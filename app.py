from flask import Flask, request, send_file, jsonify, abort
from spleeter.separator import Separator
from io import BytesIO
import requests
from dotenv import load_dotenv
import time
from pydub.utils import mediainfo
import shutil
import uuid
from pydub import AudioSegment
from flask_cors import CORS
import http.client
import json
import threading

import glob
import os
from supabase_utils import (
    upload_audio_to_supabase,
    check_file_exists_in_bucket,
    download_file_from_bucket
)


app = Flask(__name__)
CORS(app)
load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST")
DOWNLOAD_RAPIDAPI_HOST=os.getenv("DOWNLOAD_RAPIDAPI_HOST")
MP3_DOWNLOADER_HOST=os.getenv("MP3_DOWNLOADER_HOST")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_PUBLIC_KEY = os.getenv("SUPABASE_PUBLIC_KEY")
BUCKET_NAME = "mutify-vocals-audios"


separator = Separator('spleeter:2stems','multiprocess:True')
print("SEPARATOR",separator)
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
DOWNLOAD_DIR = 'downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

AUDIO_FOLDER = 'youtube-mp3-downloads'
VOCALS_FOLDER = 'audio-vocals'


def download_mp3_from_youtube(url,max_retries=3):
    # API endpoint to get the download link
    api_url = f'https://{MP3_DOWNLOADER_HOST}/dl?id={url}'
    print(api_url)
    headers = {
        'x-rapidapi-key': RAPIDAPI_KEY,  # Replace with your RapidAPI key
        'x-rapidapi-host':MP3_DOWNLOADER_HOST,  # Replace with your RapidAPI host
    }
    start_time = time.time()

    attempt = 0
    result = None
   
    response = ''
    result = ''

    while attempt < max_retries:
        try:
            print(f'ATTEMPT {attempt}')
            response = requests.get(api_url, headers=headers)
            response.raise_for_status()
            result = response.json()

            download_link = result.get('link')
            if download_link:  # Valid link received
                break
            else:
                print(f"Attempt {attempt + 1}: No valid link returned, retrying...")
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1} failed with error: {e}")
        attempt += 1

    if not result or not result.get('link'):
        print("Failed to get a valid MP3 link after retries.")
        return None, None


    try:
        # Make the request to get the MP3 link
        #response = requests.get(api_url, headers=headers)
        #response.raise_for_status()  # Check for errors in the response
        #result = response.json()  # Parse JSON response
        print(result)
        # Extract download link
        download_link = result.get('link')
        

        #file_name = result.get('title', 'downloaded_song') + '.mp3'
        file_name =f"{url}.mp3"
        file_path = os.path.join(DOWNLOAD_DIR, file_name)

        # Send a request to download the MP3 file
        mp3_response = requests.get(download_link, stream=True)
        mp3_response.raise_for_status()  # Ensure the download was successful
        
        # Determine the file path and write the content to a file
        #file_name = result.get('title', 'downloaded_song') + '.mp3'
        with open(file_path, 'wb') as file:
            for chunk in mp3_response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)
        
        # Calculate the time it took to download
        download_time = time.time() - start_time
        
        # Return the file path and download time
        #return file_name, download_time
        return ({
            'file_path': file_path,
            'download_time_seconds': download_time
        })
    
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None, None
    
 
@app.route("/separate/partial/YT", methods=["POST"])
def partialSeparateYoutubeAudio():
    data = request.json
    videoUrl = data.get("videoUrl")
    start=data.get("start","0")
    end=data.get("end","10000")

   

    if "youtube.com" in videoUrl or "youtu.be" in videoUrl:
        video_id = videoUrl.split("v=")[-1] if "v=" in videoUrl else videoUrl.split("/")[-1]
    else:
        return jsonify({"error": "Invalid YouTube URL or ID"}), 400
    
    filename = f"{video_id}_{start}_{end}.mp3"
    
    file_exists_in_storage = check_file_exists_in_bucket(filename=filename,bucket_folder=VOCALS_FOLDER)
    print('file_exists_in_storage',file_exists_in_storage)
    
    if(file_exists_in_storage):
        print('VOCAL FILE EXISTS in STORAGE',filename)
        file_data = download_file_from_bucket(VOCALS_FOLDER, filename)
        if file_data is None:
            return abort(404, description="File not found or download failed")
        return send_file(
            BytesIO(file_data),
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name=filename
        )
    else:
        print('VOCAL FILE DOES NOT EXISTS',filename)

        mp3_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
        
        if os.path.exists(mp3_path):
            print('YT MP3 ALREADY EXISTS')
            mp3_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
        else:
            print('YT MP3 DOES NOT ALREADY EXISTS, DOWNLOADING MP3')
            #audio_info = download_mp3(video_id)

            audio_info = download_mp3_from_youtube(video_id)
            if (not audio_info["file_path"])or not  os.path.exists(audio_info["file_path"]):
                    print("download path doesn't exists")
                    return jsonify({"error": "MP3 download failed"}), 500

            mp3_path = audio_info["file_path"]

        input_path_trimmed = os.path.join(UPLOAD_DIR, filename)
        output_path = os.path.join(OUTPUT_DIR, f"{video_id}_{start}_{end}")

        # Trim using pydub
        print('Starting trim')
        audio = AudioSegment.from_file(mp3_path)
        audio_segment = audio[start:end]  # 10 seconds in ms
        
        audio_segment.export(input_path_trimmed, format="mp3")
        
        # Separate trimmed audio
        print('SEPARATING startin')
        separator.separate_to_file(input_path_trimmed, OUTPUT_DIR,codec="mp3", bitrate="128k")
        vocal_path = os.path.join(output_path, "vocals.mp3")
        new_vocal_path = os.path.join(output_path, filename)
        if not os.path.exists(vocal_path):
            return jsonify({"error": "Vocal separation failed"}), 500
        

        os.rename(vocal_path, new_vocal_path)
        timer = threading.Timer(5.0, upload_audio_to_supabase, args=[new_vocal_path,True,VOCALS_FOLDER])
        timer.start()

        return send_file(new_vocal_path, mimetype="audio/mpeg", as_attachment=True, download_name=filename)


@app.route('/get_duration/<video_id>', methods=['GET'])
def get_audio_duration(video_id):
    try:
        # Look for a matching audio file with common extensions
        #file_name =f"{url}.mp3"
        #file_path = os.path.join(DOWNLOAD_DIR, file_name)
        audio_files = glob.glob(os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3"))
        if not audio_files:
            return jsonify({"error": "File not found"}), 404

        audio_file = audio_files[0]

        # Get duration using pydub/mediainfo (uses ffprobe)
        info = mediainfo(audio_file)
        duration = float(info['duration'])

        return jsonify({
            "video_id": video_id,
            "duration_seconds": duration
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
