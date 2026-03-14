from django.urls import path

from .views import ActiveTeamView, LoginView, ProfileView, SignUpView, UserAccountView

urlpatterns = [
    path("signup/", SignUpView.as_view(), name="signup"),
    path("login/", LoginView.as_view(), name="login"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("user/", UserAccountView.as_view(), name="user-account"),
    path("active-team/", ActiveTeamView.as_view(), name="active-team"),
]
