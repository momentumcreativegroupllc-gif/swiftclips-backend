from redis import Redis
from rq import Queue

from app.core.config import settings

# Create a Redis connection from the URL in .env
redis_conn = Redis.from_url(settings.REDIS_URL)

# Our main queue for SwiftClips jobs
queue = Queue("swiftclips", connection=redis_conn)
