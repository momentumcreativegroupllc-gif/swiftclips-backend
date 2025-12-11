from rq import Worker, Queue
from redis import Redis

from app.core.config import settings
from app.workers import video_jobs  # noqa: F401  # ensure jobs module is imported

redis_conn = Redis.from_url(settings.REDIS_URL)
listen = ["swiftclips"]

if __name__ == "__main__":
    queues = [Queue(name, connection=redis_conn) for name in listen]
    worker = Worker(queues, connection=redis_conn)
    worker.work()
