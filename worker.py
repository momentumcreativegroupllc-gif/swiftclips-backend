import os

# macOS: prevents fork-related Objective-C crashes
os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

from redis import Redis
from rq import SimpleWorker, Queue

from app.core.config import settings
from app.workers import video_jobs  # noqa: F401

def main():
    redis_conn = Redis.from_url(settings.REDIS_URL)
    q = Queue("swiftclips", connection=redis_conn)

    print("*** SimpleWorker listening on swiftclips (no work-horse) ***")
    worker = SimpleWorker([q], connection=redis_conn)
    worker.work(with_scheduler=False)

if __name__ == "__main__":
    main()
