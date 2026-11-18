def log_event(event, *args, **kwargs):
    print("Event:", event)
    print("Positional extras:", args)      # a tuple
    print("Keyword extras:", kwargs)       # a dict

log_event("login", "web", user="ada", ip="10.0.0.1")
