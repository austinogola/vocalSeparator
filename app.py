from flask import Flask, request, send_file, jsonify
from spleeter.separator import Separator
import os
import shutil
import uuid
from pydub import AudioSegment
from flask_cors import CORS
import http.client
import json
import requests
from dotenv import load_dotenv


app = Flask(__name__)
CORS(app)
load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST")

# Initialize Spleeter (2stems: vocals, accompaniment)
separator = Separator('spleeter:2stems')
print(separator)
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

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
    
    return jsonify({"message": "Download complete", "file_path": video_download_url})

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
            return jsonify({"error": "Vocal separation failed"}), 200

        return send_file(vocal_path, mimetype="audio/wav", as_attachment=True, download_name="vocals.wav")

    except Exception as e:
        print(e)
        print(str(e))
        return jsonify({"error": str(e)}), 200
    finally:
        if os.path.exists(input_path):
            print('DONE')
            os.remove(input_path)

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

    try:
        # Save the full audio temporarily
        file.save(input_path_full)

        # Trim to 10 seconds using pydub
        audio = AudioSegment.from_file(input_path_full)
        first_10_seconds = audio[:10 * 1000]  # 10 seconds in ms
        print('FF1')
        first_10_seconds.export(input_path_trimmed, format="wav")
        print('FF2')
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
            if os.path.exists(path) and False:
                os.remove(path)
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
        print('written')
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
