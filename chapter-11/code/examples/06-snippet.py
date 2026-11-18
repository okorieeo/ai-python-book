# function-based: simplest, explicit
def ping(request):
    return JsonResponse({"ping": "pong"})

# class-based: one method per HTTP verb, reusable through inheritance
from django.views import View

class Ping(View):
    def get(self, request):
        return JsonResponse({"ping": "pong"})
