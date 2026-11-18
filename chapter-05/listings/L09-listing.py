import redis

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

r.set("greeting", "hello", ex=60)
print(r.get("greeting"))

# A simple rate limiter: at most 5 requests per user per minute
def allowed(user_id: int, limit: int = 5) -> bool:
    key = f"rate:{user_id}"
    count = r.incr(key)
    if count == 1:
        r.expire(key, 60)       # start the 60-second window on the first request
    return count <= limit
