import yt_dlp
import sys
import os

def download_m4a(url):
    download_path = os.getcwd()

    ydl_opts = {
        # 1. Look for the best native m4a audio stream
        'format': 'bestaudio[ext=m4a]/best[ext=m4a]/best',
        
        # 2. Use 'm4a' as the final container
        'merge_output_format': 'm4a',
        
        # 3. Ensure no conversion happens (keep it fast and original)
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
        }],
        
        'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
        'quiet': False,
    }

    try:
        print(f"--- Downloading M4A (Original Quality): {url} ---")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print("\n✅ Success! M4A saved to current folder.")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python download_m4a.py <URL>")
    else:
        download_m4a(sys.argv[1])