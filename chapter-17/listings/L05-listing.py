# the chat "send message" endpoint (Chapter 29)
class MessageCreateView(APIView):
    throttle_classes = [ChatBurstThrottle]

# config/settings.py: a baseline for every other endpoint
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = [
    "rest_framework.throttling.AnonRateThrottle",
    "rest_framework.throttling.UserRateThrottle",
]
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {"anon": "60/min", "user": "300/min"}
