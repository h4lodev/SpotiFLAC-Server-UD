from flask import Flask, request, render_template, jsonify
import subprocess
import threading
import uuid
import os

# === MONKEY PATCH START (Cloudflare Bypass) ===
try:
    from SpotiFLAC.downloader.tidal import Tidal
    from curl_cffi import requests as cffi_requests
    import re

    def spoofed_get_tidal_url(self, spotify_track_id: str) -> str:
        print("🚀 Bypassing Cloudflare with curl_cffi Chrome 120 Spoofing...")
        # Gerçek bir Windows/Chrome tarayıcısı gibi davranıyoruz
        session = cffi_requests.Session(impersonate="chrome120")
        url = f"https://song.link/s/{spotify_track_id}"
        
        resp = session.get(url, timeout=15)
        match = re.search(r'https://listen\.tidal\.com/track/(\d+)', resp.text)
        
        if match:
            return match.group(0)
        raise Exception("Tidal link not found in spoofed HTML")

    # SpotiFLAC'ın orijinal fonksiyonunu RAM üzerinde eziyoruz
    Tidal.get_tidal_url_from_spotify = spoofed_get_tidal_url
    print("✅ Monkey Patch Başarılı: Cloudflare kalkanı aktif!")
except ImportError:
    print("⚠️ Monkey Patch Başarısız: SpotiFLAC veya curl_cffi bulunamadı.")
# === MONKEY PATCH END ===

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
        # SpotiFLAC'ın çalışmayan klasör parametrelerini tamamen devreden çıkarıp,
        # klasör yapısını doğrudan dosya adı formatı üzerinden (slash ile) zorluyoruz.
        if folder_structure == 'artist_album':
            fname_format = "{artist}/{album}/{title}"
        elif folder_structure == 'artist':
            fname_format = "{artist}/{title}"
        else:
            fname_format = "{artist} - {title}"

        py_script = f"""
import sys
from SpotiFLAC import SpotiFLAC

url = sys.argv[1]
output_dir = sys.argv[2]
service = sys.argv[3]
fname_format = sys.argv[4]

try:
    SpotiFLAC(
        url=url,
        output_dir=output_dir,
        services=[service],
        filename_format=fname_format,
        use_track_numbers=True  # Albümlerde şarkıların 1, 2, 3 diye sıraya girmesi için
    )
except Exception as e:
    print(str(e), file=sys.stderr)
    sys.exit(1)
"""
        process = subprocess.run(
            ["python3", "-c", py_script, url, DOWNLOAD_DIR, service, fname_format],
            capture_output=True, 
            text=True
        )
        
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