from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from . import emails
from .models import Farm, FarmMember, User
from .permissions import HasFarmRole, IsAdminRole, IsEmailVerified
from .serializers import (
    FarmSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .social import user_from_google


def issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    refresh["role"] = (
        user.role
    )  # shown to the UI; the server re-checks the database
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def sign_in_response(user):
    update_last_login(None, user)
    return Response({**issue_tokens(user), "user": UserSerializer(user).data})


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        emails.send_verification_email(user)
        return Response(
            UserSerializer(user).data, status=status.HTTP_201_CREATED
        )


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return sign_in_response(serializer.validated_data["user"])


class RefreshView(TokenRefreshView):
    """POST /auth/token/refresh: rotates the refresh token (settings.py)."""


class LogoutView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        try:
            RefreshToken(request.data.get("refresh")).blacklist()
        except Exception:
            pass  # logging out twice (or with a bad token) is not an error
        return Response(status=status.HTTP_204_NO_CONTENT)


class GoogleLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        user = user_from_google(request.data.get("id_token", ""))
        return sign_in_response(user)


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    http_method_names = ["get", "patch"]

    def get_object(self):
        return self.request.user


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        user = emails.verify_email_token(request.data.get("token", ""))
        user.email_verified = True
        user.save(update_fields=["email_verified", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ResendVerificationView(APIView):
    def post(self, request):
        if not request.user.email_verified:
            emails.send_verification_email(request.user)
        return Response(status=status.HTTP_202_ACCEPTED)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(
            email=serializer.validated_data["email"].lower(), is_active=True
        ).first()
        if user:
            emails.send_password_reset_email(user)
        return Response(
            status=status.HTTP_202_ACCEPTED
        )  # the same answer either way


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = emails.user_from_reset_link(data["uid"], data["token"])
        try:  # the new password must pass the same rules as registration
            validate_password(data["new_password"], user)
        except DjangoValidationError as exc:
            raise ValidationError({"new_password": list(exc.messages)})
        user.set_password(
            data["new_password"]
        )  # also invalidates the reset link
        user.save(update_fields=["password", "updated_at"])
        for outstanding in OutstandingToken.objects.filter(user=user):
            try:  # sign out every device
                RefreshToken(outstanding.token).blacklist()
            except Exception:
                pass
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserList(generics.ListAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = UserSerializer
    queryset = User.objects.order_by("id")


class FarmList(generics.ListCreateAPIView):
    serializer_class = FarmSerializer
    permission_classes = [IsAuthenticated, IsEmailVerified]

    def get_queryset(self):
        return Farm.objects.filter(members__user=self.request.user).order_by(
            "id"
        )

    @transaction.atomic
    def perform_create(self, serializer):
        farm = serializer.save()
        FarmMember.objects.create(
            farm=farm, user=self.request.user, role="owner"
        )


class FarmDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = FarmSerializer
    permission_classes = [IsAuthenticated, HasFarmRole]
    lookup_field = "public_id"
    http_method_names = ["get", "patch", "delete"]
    roles_for_method = {
        "GET": {"owner", "manager", "worker"},
        "PATCH": {"owner", "manager"},
        "DELETE": {"owner"},
    }

    def get_queryset(
        self,
    ):  # non-members get 404: we do not reveal other farms
        return Farm.objects.filter(members__user=self.request.user)
