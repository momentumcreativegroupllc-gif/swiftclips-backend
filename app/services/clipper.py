import subprocess

def cut_clip(input_path: str, output_path: str, start_time: float, duration: float = 4.0):
    """
    Browser-safe clip:
    - Re-encode to H.264 + AAC
    - Move moov atom to the front so it streams in browsers (faststart)
    """
    start = max(start_time - 1.0, 0)

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(start),
        "-i", input_path,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]
    subprocess.run(cmd, check=True)
