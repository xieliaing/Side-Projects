import yt_dlp

video_url = "https://youtu.be/Ej7SK6aQobs?si=nEc6kbLWJHxhEjBQ"

ydl_opts = {
    'format': 'bestvideo+bestaudio/best',  # Get best quality
    'outtmpl': '%(title)s.%(ext)s'         # Save with title name
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    ydl.download([video_url])
