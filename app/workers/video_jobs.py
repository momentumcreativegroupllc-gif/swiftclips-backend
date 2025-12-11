from time import sleep

def process_video_job(video_id: str, storage_url: str) -> dict:
    """
    Placeholder video processing job.
    Later this will:
      - download the video
      - run transcription
      - detect scenes
      - cut clips
    For now it just simulates work.
    """
    print(f"[worker] Starting processing for {video_id} at {storage_url}")
    sleep(5)  # simulate heavy work
    print(f"[worker] Finished processing for {video_id}")
    return {"video_id": video_id, "status": "processed"}
