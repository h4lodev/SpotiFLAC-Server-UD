from flask import Flask, request, render_template, jsonify
import subprocess
import threading
import uuid
import os

app = Flask(__name__)
DOWNLOAD_DIR = "/downloads"

tasks = {}

# Dil sözlüğü
MESSAGES = {
    'tr': {
        'no_url': "Lütfen bir Spotify linki girin.",
        'processing': "İndirme arka planda devam ediyor...",
        'completed': "İndirme başarıyla tamamlandı!",
        'error': "Bir hata oluştu.",
        'not_found': "Görev bulunamadı."
    },
    'en': {
        'no_url': "Please enter a Spotify link.",
        'processing': "Download is processing in the background...",
        'completed': "Download completed successfully!",
        'error': "An error occurred.",
        'not_found': "Task not found."
    }
}

def run_download(task_id, url, folder_structure, service, lang):
    try:
        cmd = ["spotiflac", url, DOWNLOAD_DIR]
        
        if service in ['tidal', 'qobuz', 'deezer', 'amazon']:
            cmd.extend(["--service", service])
            
        if folder_structure == 'artist_album':
            cmd.extend(["--use-artist-subfolders", "--use-album-subfolders"])
        elif folder_structure == 'artist':
            cmd.extend(["--use-artist-subfolders"])

        process = subprocess.run(cmd, capture_output=True, text=True)
        
        if process.returncode == 0:
            tasks[task_id] = {"status": "completed", "message": MESSAGES[lang]['completed'], "log": process.stdout}
        else:
            tasks[task_id] = {"status": "error", "message": MESSAGES[lang]['error'], "log": process.stderr}
            
    except Exception as e:
        tasks[task_id] = {"status": "error", "message": str(e), "log": ""}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url')
    lang = request.form.get('lang', 'tr')
    
    if not url:
        return jsonify({"status": "error", "message": MESSAGES[lang]['no_url']}), 400

    folder_structure = request.form.get('folder_structure', 'artist_album')
    service = request.form.get('service', 'tidal')

    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "processing", "message": MESSAGES[lang]['processing'], "log": ""}
    
    thread = threading.Thread(target=run_download, args=(task_id, url, folder_structure, service, lang))
    thread.start()
    
    return jsonify({"status": "started", "task_id": task_id})

@app.route('/status/<task_id>', methods=['GET'])
def status(task_id):
    lang = request.args.get('lang', 'tr')
    task = tasks.get(task_id)
    if not task:
        return jsonify({"status": "error", "message": MESSAGES[lang]['not_found']}), 404
    return jsonify(task)

@app.route('/files', methods=['GET'])
def list_files():
    files_list = []
    for root, dirs, files in os.walk(DOWNLOAD_DIR):
        for file in files:
            if file.lower().endswith(('.flac', '.mp3', '.m4a', '.ogg', '.wav')):
                rel_dir = os.path.relpath(root, DOWNLOAD_DIR)
                if rel_dir == ".":
                    files_list.append(file)
                else:
                    files_list.append(os.path.join(rel_dir, file))
                    
    return jsonify({"files": sorted(files_list)})