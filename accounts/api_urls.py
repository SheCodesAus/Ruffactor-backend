from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AllKudosByUserView,
    AnalyticsView,
    ReceivedKudosByUserView,
    GivenKudosByUserView,
    KudosViewSet,
    PublicKudosListView,
    SkillCategoryViewSet,
    TeamViewSet,
    UserListView,
    UserSearchView
)

router = DefaultRouter()
router.register(r"teams", TeamViewSet, basename="team")
router.register(r"skills", SkillCategoryViewSet, basename="skill")
router.register(r"kudos", KudosViewSet, basename="kudos")

urlpatterns = [
    path("users/", UserListView.as_view(), name="user-list"),
    path("users/search/", UserSearchView.as_view(), name="user-search"),
    path("kudos/public/", PublicKudosListView.as_view(), name="kudos-public"),
    path("kudos/analytics/", AnalyticsView.as_view(), name="kudos-analytics"),
    path(
        "users/<int:pk>/kudos/",
        AllKudosByUserView.as_view(),
        name="user-all-kudos",
        ),
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
