# created using ChatGPT on Feb 18,2022
# with minor tweak in handling output file name

import argparse
import os
import ffmpeg
from pytube import YouTube

# Define command line arguments
parser = argparse.ArgumentParser(description='Download and convert a YouTube video to MP3.')
parser.add_argument('url', type=str, help='The YouTube video URL.')
parser.add_argument('--output-dir', type=str, default='./', help='The output directory for the MP3 file.')

# Parse command line arguments
args = parser.parse_args()

print(args.url)
print(args.output_dir)

# Create output directory if it doesn't exist
if not os.path.exists(args.output_dir):
    os.makedirs(args.output_dir)

# Download video using pytube
print(f'Downloading video from {args.url}...')
yt = YouTube(args.url)
video = yt.streams.get_highest_resolution()
video.download(args.output_dir)




# Extract audio from video using ffmpeg
print('Extracting audio from video...')
video_path = os.path.join(args.output_dir, video.default_filename)
# Remove backslash from title, otherwise could cause exception when saving mp3 file from ffmpeg. 
#audio_filename = yt.title.replace("/", "_").replace("\\", "").mp3
audio_path = os.path.join(args.output_dir, yt.title.replace("/", "_").replace("\\", "").replace(".", "")+'.mp3')
(
    ffmpeg
    .input(video_path, threads=4)
    .output(audio_path, format='mp3', acodec='libmp3lame', threads=1)
    .run()
)

print(f'Audio file saved to {audio_path}')