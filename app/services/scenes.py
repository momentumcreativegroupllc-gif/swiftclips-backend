import re
import subprocess

PTS_RE = re.compile(r"pts_time:(\d+(\.\d+)?)")

def detect_scene_timestamps(video_path: str, threshold: float = 0.35):
    """
    Detect scene change timestamps using ffmpeg select(scene) + showinfo.
    Returns sorted unique timestamps (seconds).
    """
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i", video_path,
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null",
        "-"
    ]

    # ffmpeg prints filter logs to stderr
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        # keep it short but useful
        tail = "\n".join(proc.stderr.splitlines()[-30:])
        raise RuntimeError(f"ffmpeg scene detect failed (code={proc.returncode}). Tail:\n{tail}")

    timestamps = []
    for line in proc.stderr.splitlines():
        m = PTS_RE.search(line)
        if m:
            timestamps.append(float(m.group(1)))

    return sorted(set(timestamps))
