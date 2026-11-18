def get_dashboard_stats(user_id):
    key = f"stats:{user_id}"
    cached = cache.get(key)
    if cached is not None:                 # 1. hit: return immediately
        return cached
    stats = compute_stats_from_database(user_id)    # 2. miss: do the expensive work
    cache.set(key, stats, ttl=300)         # 3. store for 5 minutes
    return stats
