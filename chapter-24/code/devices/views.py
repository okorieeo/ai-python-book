from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .models import PushDevice
from .serializers import DeviceSerializer

class DeviceCreate(generics.GenericAPIView):
    serializer_class = DeviceSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "devices"
    pagination_class = None

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # An upsert keyed on the token. Safe to call at every app launch, and it
        # moves the token to the current account if the phone changed hands.
        device, created = PushDevice.objects.update_or_create(
            token=data["token"],
            defaults={
                "user": request.user,
                "platform": data["platform"],
                "device_name": data.get("device_name", ""),
                "is_active": True,
            },
        )
        return Response(
            DeviceSerializer(device).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

class DeviceDetail(generics.DestroyAPIView):
    lookup_field = "public_id"

    def get_queryset(self):
        return self.request.user.push_devices.all()  # someone else's id is a 404
