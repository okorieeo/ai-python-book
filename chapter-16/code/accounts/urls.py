from django.urls import path

from . import views

urlpatterns = [
    path("auth/register", views.RegisterView.as_view()),
    path("auth/login", views.LoginView.as_view()),
    path("auth/token/refresh", views.RefreshView.as_view()),
    path("auth/logout", views.LogoutView.as_view()),
    path("auth/google", views.GoogleLoginView.as_view()),
    path("auth/verify-email", views.VerifyEmailView.as_view()),
    path("auth/resend-verification", views.ResendVerificationView.as_view()),
    path("auth/password-reset", views.PasswordResetRequestView.as_view()),
    path(
        "auth/password-reset/confirm",
        views.PasswordResetConfirmView.as_view(),
    ),
    path("me", views.MeView.as_view()),
    path("admin/users", views.AdminUserList.as_view()),
    path("farms", views.FarmList.as_view()),
    path("farms/<uuid:public_id>", views.FarmDetail.as_view()),
]
