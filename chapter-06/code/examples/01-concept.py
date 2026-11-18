# BAD: everything inside the view. Hard to test, impossible to reuse
def send_message(request):
    user = request.user
    if user.plan == "free" and Message.objects.filter(user=user, today=True).count() >= 20:
        return Response({"detail": "Limit reached"}, status=429)
    answer = requests.post("https://ai-provider...", json={...}).json()["text"]
    Message.objects.create(user=user, content=answer)
    return Response({"answer": answer})

# GOOD: the view only translates HTTP; the rules live in a service
def send_message(request):
    serializer = MessageSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        reply = chat_service.send(user=request.user, text=serializer.validated_data["text"])
    except DailyLimitReached:
        return Response({"detail": "Limit reached"}, status=429)
    return Response(ReplySerializer(reply).data)
