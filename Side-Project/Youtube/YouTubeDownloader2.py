#created with the help of ChatGPT on 4/15/2024
# update 7/5/2025: added command line parameter parser
#
import yt_dlp
import argparse
import os



# Define command line arguments
parser = argparse.ArgumentParser(description='Download and convert a YouTube video to MP3.')
parser.add_argument('url', type=str, help='The YouTube video URL.')
parser.add_argument('--output-dir', type=str, default='./', help='The output directory for the MP3 file.')

# Parse command line arguments
args = parser.parse_args()

print(args.url)
print(args.output_dir)

video_url = args.url
#video_url = "https://youtu.be/Ej7SK6aQobs?si=nEc6kbLWJHxhEjBQ"

ydl_opts = {
    'format': 'bestvideo+bestaudio/best',  # Get best quality
    'outtmpl': '%(title)s.%(ext)s'         # Save with title name
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    ydl.download([video_url])
