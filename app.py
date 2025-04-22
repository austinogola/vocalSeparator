from flask import Flask, request, send_file, jsonify
from spleeter.separator import Separator
import shutil
import uuid
from pydub import AudioSegment
from flask_cors import CORS
import http.client
import json
import requests
from dotenv import load_dotenv
import time
from pydub.utils import mediainfo
import glob
import os
from supabase import create_client, Client
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
#print(SUPABASE_PUBLIC_KEY)
#print(SUPABASE_URL)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_PUBLIC_KEY)
# Initialize Spleeter (2stems: vocals, accompaniment)
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

result = upload_audio_to_supabase("defaultVocals.wav", delete_after_upload=True,bucket_folder=AUDIO_FOLDER)
print(result)


#spleeter separate -i audio_example.mp3 -c mp3 -b 128k
def download_mp3(video_id ):
    download_url2 = 'https://youtube-mp3-audio-video-downloader.p.rapidapi.com/download-mp3/R1F7nAomdn8?quality=low'
    #download_url = f"https://{DOWNLOAD_RAPIDAPI_HOST}/download-mp3/{video_id}?quality=low"
    download_url = f"https://{DOWNLOAD_RAPIDAPI_HOST}/download-m4a/{video_id}"
    print(download_url)
    #print(download_url2)
    headers = {
        'x-rapidapi-key': RAPIDAPI_KEY,
        'x-rapidapi-host': DOWNLOAD_RAPIDAPI_HOST
    }
    try:
        start_time = time.time()

        response = requests.get(download_url, headers=headers, stream=True)
        print(response)
        #print(response.text)
        if response.status_code != 200:
            return {'error': 'Failed to download file'}

        filename = f"{video_id}.mp3"
        filepath = os.path.join(DOWNLOAD_DIR, filename)

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)

        print('DONE WRITING')
        elapsed_time = time.time() - start_time

        return ({
            'file_path': filepath,
            'download_time_seconds': round(elapsed_time, 2)
        })

    except Exception as e:
        return jsonify({'error': str(e)})


#PP=download_mp3('R1F7nAomdn8')
#print(PP)

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



#file_path, download_time = download_mp3_from_youtube("m1EZG6RZsyg")
#if file_path:
  #  print(f"Downloaded file: {file_path}")
   # print(f"Download time: {download_time:.2f} seconds")
#else:
 #   print('ERROR')


def parse_time(time_input):
    if isinstance(time_input, int) or time_input.isdigit():
        return int(time_input) * 1000  # convert to milliseconds
    parts = list(map(int, time_input.split(":")))
    seconds = 0
    if len(parts) == 3:
        seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        seconds = parts[0] * 60 + parts[1]
    elif len(parts) == 1:
        seconds = parts[0]
    return seconds * 1000  # to milliseconds

def get_video_info(video_id):
    conn = http.client.HTTPSConnection(RAPIDAPI_HOST)
    headers = {
        'x-rapidapi-key': RAPIDAPI_KEY,
        'x-rapidapi-host': RAPIDAPI_HOST
    }
    conn.request("GET", f"/dl?id={video_id}", headers=headers)
    res = conn.getresponse()
    data = res.read()
    conn.close()
    return data.decode("utf-8")

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


@app.route("/download/audio/YT", methods=["POST"])
def downloadYoutubeAudio():
    data = request.json
    videoUrl = data.get("videoUrl")
    
    if "youtube.com" in videoUrl or "youtu.be" in videoUrl:
        video_id = videoUrl.split("v=")[-1] if "v=" in videoUrl else videoUrl.split("/")[-1]
    else:
        return jsonify({"error": "Invalid YouTube URL or ID"}), 400

    mp3_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
    if os.path.exists(mp3_path):
       return send_file(mp3_path, mimetype="audio/mpeg", as_attachment=True, download_name=f"{video_id}.mp3")

    audio_info = download_mp3(video_id)
    print(audio_info)
    if (not audio_info["file_path"])or not  os.path.exists(audio_info["file_path"]):
            print("download path doesn't exists")
            return jsonify({"error": "MP3 download failed"}), 500

    return send_file(audio_info["file_path"], mimetype="audio/mpeg", as_attachment=True, download_name=f"{video_id}.mp3")


@app.route("/separateYT", methods=["POST"])
def separateYoutube():
    data = request.json
    videoUrl = data.get("videoUrl")
    
    if "youtube.com" in videoUrl or "youtu.be" in videoUrl:
        video_id = videoUrl.split("v=")[-1] if "v=" in videoUrl else videoUrl.split("/")[-1]
    else:
        return jsonify({"error": "Invalid YouTube URL or ID"}), 400
    
    video_info = get_video_info(video_id)
    video_data = json.loads(video_info)  # Convert string response to dict
    
    if video_data.get("status") != "OK":
        return jsonify({"error": "Failed to retrieve video info"}), 500
    
    formats = video_data.get("adaptiveFormats", [])
    sorted_formats = sorted(formats, key=lambda x: x.get("bitrate", 0))
    best_format = sorted_formats[1] if len(sorted_formats) > 1 else None
    #best_format = max(formats, key=lambda x: x.get("bitrate", 0), default=None)
    
    if not best_format:
        return jsonify({"error": "No available formats"}), 500
    
    video_download_url = best_format["url"]
    filename = f"{video_id}.mp4"
   # file_path = download_video(video_download_url, filename)
    
    return jsonify({"message": "complete", "media_url": video_download_url})


@app.route('/separate', methods=['POST'])
def separate():
    print('separate path')
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    print('File is here too')
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    file_id = str(uuid.uuid4())
    print('fileId',file_id)
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}.mp3")
    output_path = os.path.join(OUTPUT_DIR, file_id)
    print('OUTPUT PATH CRAETED')
    try:
        file.save(input_path)
        print('file saved input', input_path)
        separator.separate_to_file(input_path, OUTPUT_DIR)
        print('separatot file first')
        vocal_path = os.path.join(output_path, "vocals.wav")
        print(vocal_path,"created vocal path")
        if not os.path.exists(vocal_path):
            print("os path doesn't exists")
            return jsonify({"error": "Vocal separation failed"}), 500

        return send_file(vocal_path, mimetype="audio/wav", as_attachment=True, download_name="vocals.wav")

    except Exception as e:
        print(e)
        print(str(e))
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(input_path):
            print('DONE')
            os.remove(input_path)



@app.route("/separate/partial/YT", methods=["POST"])
def partialSeparateYoutubeAudio():
    data = request.json
    videoUrl = data.get("videoUrl")
    start=data.get("start","0")
    end=data.get("end","10000")

    #start = parse_time(start)
    #end = parse_time(end)

    if "youtube.com" in videoUrl or "youtu.be" in videoUrl:
        video_id = videoUrl.split("v=")[-1] if "v=" in videoUrl else videoUrl.split("/")[-1]
    else:
        return jsonify({"error": "Invalid YouTube URL or ID"}), 400

    mp3_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
    if os.path.exists(mp3_path):
       print('ALREADY EXISTS')
       mp3_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
    else:
      print('DOES NOT ALREADY EXISTS, DOWNLOADING MP3')
      #audio_info = download_mp3(video_id)

      audio_info = download_mp3_from_youtube(video_id)
      print(audio_info)
      if (not audio_info["file_path"])or not  os.path.exists(audio_info["file_path"]):
            print("download path doesn't exists")
            return jsonify({"error": "MP3 download failed"}), 500

      mp3_path = audio_info["file_path"]

    input_path_trimmed = os.path.join(UPLOAD_DIR, f"{video_id}_{start}_{end}.mp3")
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
    print('vocal path',vocal_path)

    if not os.path.exists(vocal_path):
        return jsonify({"error": "Vocal separation failed"}), 500

    return send_file(vocal_path, mimetype="audio/mpeg", as_attachment=True, download_name="vocals_preview.mp3")

@app.route('/separate/preview', methods=['POST'])
def separate_preview():
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    file_id = str(uuid.uuid4())
    input_path_full = os.path.join(UPLOAD_DIR, f"{file_id}_full.mp3")
    input_path_trimmed = os.path.join(UPLOAD_DIR, f"{file_id}_10s.mp3")
    output_path = os.path.join(OUTPUT_DIR, f"{file_id}_10s")
    print('preview path',output_path)
    try:
        # Save the full audio temporarily
        file.save(input_path_full)

        # Trim to 10 seconds using pydub
        audio = AudioSegment.from_file(input_path_full)
        first_20_seconds = audio[:20 * 1000]  # 10 seconds in ms
        print('SEPARATE PRE 1')
        first_20_seconds.export(input_path_trimmed, format="wav")
        print('SEPARATE PRE 2')
        # Separate trimmed audio
        separator.separate_to_file(input_path_trimmed, OUTPUT_DIR)
        vocal_path = os.path.join(output_path, "vocals.wav")
        print('vocal path',vocal_path)
        if not os.path.exists(vocal_path):
            return jsonify({"error": "Vocal separation failed"}), 500

        return send_file(vocal_path, mimetype="audio/wav", as_attachment=True, download_name="vocals_preview.wav")

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        for path in [input_path_full, input_path_trimmed]:
            if os.path.exists(path):
                os.remove(path)


@app.route('/test', methods=['POST'])
def testEndpoint():
   data = request.json
   type0f=''
   if not data or 'typeOf' not in data:
       typeOf = 'aud'
   else:
       typeOf = data.get('typeOf','aud')

   # Name of the file in your app root directory
   #filename = 'defaultVocals.wav'
    
   # Absolute path to the root directory of the app
   #root_dir = os.path.abspath(os.path.dirname(__file__))
    
   # Send the file from root
   #return send_from_directory(root_dir, filename, as_attachment=True)
   file_path = os.path.join(os.path.dirname(__file__), 'defaultVocals.wav')
   if typeOf == 'aud':
       return send_file(file_path, as_attachment=True,download_name="defaultVocals.wav")
       #return  file_path = os.path.join(os.path.dirname(__file__), 'example.txt')
       #return send_file(vocal_path, mimetype="audio/wav", as_attachment=True, download_name="vocals_from_url.wav")
   else:
       #return send_file(vocal_path, mimetype="audio/wav", as_attachment=True, download_name="vocals_from_url.wav")
       return send_file(file_path, as_attachment=True,download_name="defaultVocals.wav")


@app.route('/separate/url', methods=['POST'])
def separate_from_url():
    data = request.json
    if not data or 'url' not in data:
        return jsonify({"error": "Missing 'url' in request body"}), 400

    url = data['url']
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}.mp3")
    output_path = os.path.join(OUTPUT_DIR, file_id)

    try:
        # Download audio file
        headers = {
                   "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                 "AppleWebKit/537.36 (KHTML, like Gecko) "
                                 "Chrome/113.0.0.0 Safari/537.36",
                   "Accept": "*/*",
                   "Connection": "keep-alive"
        }
        print("getting urls with headers", headers)
        r = requests.request("GET",url, headers=headers,data={}, stream=True)
        print(r)
        if r.status_code != 200:
            return jsonify({"error": "Failed to download audio from URL"}), 400

        with open(input_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        # Separate
        print('WRITTEN URL SUCCESSFULLY')
        separator.separate_to_file(input_path, OUTPUT_DIR)
        vocal_path = os.path.join(output_path, "vocals.wav")

        if not os.path.exists(vocal_path):
            return jsonify({"error": "Vocal separation failed"}), 500

        return send_file(vocal_path, mimetype="audio/wav", as_attachment=True, download_name="vocals_from_url.wav")

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
