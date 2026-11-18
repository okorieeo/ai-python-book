from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsEmailVerified

from .outbound import new_secret
from .serializers import EndpointSerializer


class EndpointList(generics.ListCreateAPIView):
    serializer_class = EndpointSerializer
    permission_classes = [IsAuthenticated, IsEmailVerified]

    def get_queryset(self):
        return self.request.user.endpoints.order_by("-id")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        secret = new_secret()
        endpoint = serializer.save(user=request.user, secret=secret)
        data = {**EndpointSerializer(endpoint).data, "secret": secret}
        return Response(data, status=status.HTTP_201_CREATED)  # shown ONCE


class EndpointDetail(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]
    lookup_field = "public_id"

    def get_queryset(self):
        return self.request.user.endpoints.all()
