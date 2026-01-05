import yt_dlp
import sys
import os

def download_youtube_audio(url):
    # Set the destination folder (Current Directory)
    download_path = os.getcwd()

    ydl_opts = {
        # Select the best audio quality available
        'format': 'bestaudio/best',
        
        # Post-processor: Use FFmpeg to convert the audio to MP3
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        
        # Output template: Title.extension
        'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
        
        # Clean up: delete the original webm/m4a file after converting to mp3
        'keepvideo': False,
        
        'quiet': False,
    }

    try:
        print(f"--- Initializing Download: {url} ---")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print("\n✅ Success! Audio saved to your current folder.")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python download_audio.py <YOUTUBE_URL>")
    else:
        video_url = sys.argv[1]
        download_youtube_audio(video_url)