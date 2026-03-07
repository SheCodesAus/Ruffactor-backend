from django.urls import path

from .views import ActiveTeamView, LoginView, SignUpView

urlpatterns = [
    path("signup/", SignUpView.as_view(), name="signup"),
    path("login/", LoginView.as_view(), name="login"),
    path("active-team/", ActiveTeamView.as_view(), name="active-team"),
]
