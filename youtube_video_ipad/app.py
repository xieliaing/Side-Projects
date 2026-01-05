import os
import time
import re
from flask import Flask, request, jsonify, send_file
from yt_dlp import YoutubeDL
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- CONFIGURATION ---
DOWNLOAD_FOLDER = 'downloads'
PROMO_CODE = "98033"
FILE_EXPIRY_SECONDS = 3600  # Delete files after 1 hour

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

def clean_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

# --- BACKGROUND CLEANUP ---
def cleanup_old_files():
    now = time.time()
    for filename in os.listdir(DOWNLOAD_FOLDER):
        file_path = os.path.join(DOWNLOAD_FOLDER, filename)
        if os.path.isfile(file_path):
            if now - os.path.getmtime(file_path) > FILE_EXPIRY_SECONDS:
                try:
                    os.remove(file_path)
                except:
                    pass

scheduler = BackgroundScheduler()
scheduler.add_job(func=cleanup_old_files, trigger="interval", minutes=15)
scheduler.start()

# --- ROUTES ---

@app.route('/')
def index():
    return send_file('index.html')

@app.route('/get_info', methods=['POST'])
def get_info():
    video_url = request.json.get('url')
    if not video_url:
        return jsonify({'error': 'No URL provided'}), 400

    ydl_opts = {'quiet': True, 'noplaylist': True}
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            # download=False is the key: it's nearly instant
            info = ydl.extract_info(video_url, download=False)
            
            # Extract unique resolutions from formats
            # We filter for heights that exist and are common (360, 480, 720, 1080)
            formats = info.get('formats', [])
            available_res = sorted(list(set(
                f['height'] for f in formats 
                if f.get('height') and f['height'] <= 1080
            )), reverse=True)

            return jsonify({
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration_string'),
                'resolutions': available_res
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/convert', methods=['POST'])
def convert_video():
    data = request.json
    video_url = data.get('url')
    user_code = data.get('code', '').strip().lower()
    res = data.get('resolution', '720') # Default to 720p
    print(f"DEBUG: Received resolution request for: {res}") # Check your console!

    if not video_url:
        return jsonify({'error': 'No URL provided'}), 400

    # TURBO DOWNLOAD-ONLY OPTIONS (No FFmpeg re-encoding)
    ydl_opts = {
        # Using a more robust format string for iPad compatibility
        'format': f'bestvideo[height<={res}][ext=mp4]/best[height<={res}][ext=mp4]/best',
        #'merge_output_format': 'mp4',
        'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(id)s_%(title)s.%(ext)s'),
        'noplaylist': True,
        'cachedir': False,
        'force_overwrites': True,
        'overwrites': True,
    }

    # Handle Promotion Code (Full vs 3-Min Trial)
    if user_code != PROMO_CODE:
        # Limited to first 180 seconds
        ydl_opts['download_ranges'] = lambda info_dict, self: [{'start_time': 0, 'end_time': 180}]
        ydl_opts['force_keyframes_at_cuts'] = True

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            full_path = ydl.prepare_filename(info)
            filename = os.path.basename(full_path)
            
        return jsonify({
            'status': 'success', 
            'download_url': f"/download/{filename}",
            'title': info.get('title', 'Video'),
            'mode': 'full' if user_code == PROMO_CODE else 'trial'
        })

    except Exception as e:
        # Parse common errors (DRM, Private, etc.)
        err_str = clean_ansi(str(e)).lower()
        if "drm" in err_str or "protected" in err_str:
            msg = "This video is DRM protected and cannot be downloaded."
        elif "private" in err_str:
            msg = "This video is private."
        else:
            msg = f"Error: {clean_ansi(str(e))}"
        return jsonify({'error': msg}), 500

@app.route('/download/<path:filename>')
def download_file(filename):
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return jsonify({'error': 'File expired or not found'}), 404

if __name__ == '__main__':
    # For local testing; AWS uses Gunicorn
    app.run(host='0.0.0.0', port=5000)
