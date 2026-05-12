import redis
from app.settings.config import Settings

settings = Settings()

redis_cache = redis.Redis.from_url(settings.redis_url_cache, decode_responses=True)
