import subprocess
import sys
import os
from pathlib import Path

YTDLP = "yt-dlp.exe"
FFMPEG = "ffmpeg.exe"

def run_and_capture(cmd):
    """
    Run a command and capture stdout.
    """
    print(" ".join(cmd))
    result = subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return result.stdout.strip()

def download_with_original_name(url):
    """
    Download the best available source and return the final file path.
    """
    cmd = [
        YTDLP,
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "--print", "after_move:filepath",
        url
    ]

    output = run_and_capture(cmd)
    return Path(output)

def transcode_for_old_ipad(input_file: Path):
    """
    Transcode to old-iPad-compatible MP4 (720p max).
    """
    output_file = input_file.with_name(
        f"{input_file.stem}_ipad.mp4"
    )

    cmd = [
        FFMPEG,
        "-y",
        "-i", str(input_file),

        # Video
        "-vf", "scale='min(1280,iw)':-2:flags=lanczos",
        #"-c:v", "libx264", #CPU-based
        "-c:v", "h264_nvenc", #GPU-based
        "-profile:v", "baseline",
        "-level", "3.1",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-preset", "fast",
        "-crf", "22",

        # Audio
        "-c:a", "aac",
        "-b:a", "128k",
        "-ac", "2",
        "-ar", "44100",

        # Container flags
        "-movflags", "+faststart",

        str(output_file)
    ]

    print(" ".join(cmd))
    subprocess.run(cmd, check=True)

    return output_file

def main():
    if len(sys.argv) < 2:
        print("Usage: python youtube_to_ipad.py <youtube_url>")
        sys.exit(1)

    url = sys.argv[1]

    print("Downloading YouTube source...")
    source_file = download_with_original_name(url)

    print(f"Source file: {source_file}")

    print("Transcoding for old iPad compatibility...")
    ipad_file = transcode_for_old_ipad(source_file)

    print("\nDone.")
    print(f"iPad-compatible file: {ipad_file}")

if __name__ == "__main__":
    main()