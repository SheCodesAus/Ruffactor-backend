from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    GivenKudosByUserView,
    KudosViewSet,
    PublicKudosListView,
    ReceivedKudosByUserView,
    SkillCategoryViewSet,
    TeamViewSet,
)

router = DefaultRouter()
router.register(r"teams", TeamViewSet, basename="team")
router.register(r"skills", SkillCategoryViewSet, basename="skill")
router.register(r"kudos", KudosViewSet, basename="kudos")

urlpatterns = [
    path("kudos/public/", PublicKudosListView.as_view(), name="kudos-public"),
    path(
        "users/<int:pk>/received-kudos/",
        ReceivedKudosByUserView.as_view(),
        name="user-received-kudos",
    ),
    path(
        "users/<int:pk>/given-kudos/",
        GivenKudosByUserView.as_view(),
        name="user-given-kudos",
    ),
    path("", include(router.urls)),
]
