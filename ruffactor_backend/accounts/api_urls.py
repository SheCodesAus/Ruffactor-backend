from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import KudosViewSet, PublicKudosListView, SkillCategoryViewSet, TeamViewSet

router = DefaultRouter()
router.register(r"teams", TeamViewSet, basename="team")
router.register(r"skills", SkillCategoryViewSet, basename="skill")
router.register(r"kudos", KudosViewSet, basename="kudos")

urlpatterns = [
    path("kudos/public/", PublicKudosListView.as_view(), name="kudos-public"),
    path("", include(router.urls)),
]
