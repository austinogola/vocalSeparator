from flask import Flask, request, send_file, jsonify
from spleeter.separator import Separator
import os
import shutil
import uuid
from pydub import AudioSegment
app = Flask(__name__)

# Initialize Spleeter (2stems: vocals, accompaniment)
separator = Separator('spleeter:2stems')
print(separator)
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

@app.route('/')
def home():
    return jsonify({"message": "Spleeter Server is running!"})

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
