import subprocess

def get_duration_seconds(video_path: str) -> float:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    out = subprocess.check_output(cmd).decode().strip()
    return float(out)
