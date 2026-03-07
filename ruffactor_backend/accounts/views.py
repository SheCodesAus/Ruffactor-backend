from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.contrib.auth import login as auth_login
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Kudos, SkillCategory, Team, TeamMembership
from .serializers import (
    KudosReadSerializer,
    KudosWriteSerializer,
    LoginSerializer,
    SignUpSerializer,
    SkillCategorySerializer,
    TeamMembershipSerializer,
    TeamMembershipWriteSerializer,
    TeamSerializer,
)


class SignUpView(generics.CreateAPIView):
    serializer_class = SignUpSerializer
    permission_classes = [permissions.AllowAny]


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        auth_login(request, user)

        return Response(
            {
                "message": "Login successful.",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                },
            },
            status=status.HTTP_200_OK,
        )


class IsSenderOrStaff(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_staff or obj.sender_id == request.user.id


class TeamViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = TeamSerializer
    queryset = Team.objects.all()

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated(), permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        if self.request.user.is_staff:
            return Team.objects.all()
        return Team.objects.filter(memberships__user=self.request.user).distinct()

    def perform_create(self, serializer):
        team = serializer.save()
        TeamMembership.objects.get_or_create(
            team=team,
            user=self.request.user,
            defaults={"role": TeamMembership.Role.ADMIN},
        )

    def _assert_team_admin_or_staff(self, team):
        if self.request.user.is_staff:
            return
        is_team_admin = TeamMembership.objects.filter(
            team=team,
            user=self.request.user,
            role=TeamMembership.Role.ADMIN,
        ).exists()
        if not is_team_admin:
            raise PermissionDenied("You must be a team admin or staff to manage members.")

    @action(detail=True, methods=["post"], url_path="members")
    def add_member(self, request, pk=None):
        team = get_object_or_404(Team, pk=pk)
        self._assert_team_admin_or_staff(team)
        serializer = TeamMembershipWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        membership, created = TeamMembership.objects.update_or_create(
            team=team,
            user=serializer.validated_data["user"],
            defaults={"role": serializer.validated_data["role"]},
        )
        response_serializer = TeamMembershipSerializer(membership)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @add_member.mapping.delete
    def remove_member(self, request, pk=None):
        team = get_object_or_404(Team, pk=pk)
        self._assert_team_admin_or_staff(team)
        user_id = request.query_params.get("user_id")
        if not user_id:
            return Response(
                {"detail": "user_id query param is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        membership = TeamMembership.objects.filter(team=team, user_id=user_id).first()
        if not membership:
            return Response(status=status.HTTP_404_NOT_FOUND)
        membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"members/(?P<user_id>[^/.]+)",
    )
    def remove_member_by_path(self, request, pk=None, user_id=None):
        team = get_object_or_404(Team, pk=pk)
        self._assert_team_admin_or_staff(team)
        membership = TeamMembership.objects.filter(team=team, user_id=user_id).first()
        if not membership:
            return Response(status=status.HTTP_404_NOT_FOUND)
        membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SkillCategoryViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SkillCategorySerializer
    queryset = SkillCategory.objects.all()

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated(), permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        if self.action == "list":
            return SkillCategory.objects.filter(is_active=True)
        return SkillCategory.objects.all()


class KudosViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsSenderOrStaff]

    def get_queryset(self):
        user = self.request.user
        queryset = (
            Kudos.objects.select_related("sender", "recipient")
            .prefetch_related("skills", "target_teams")
            .filter(
                Q(visibility=Kudos.Visibility.PUBLIC)
                | Q(sender=user)
                | Q(recipient=user)
                | Q(
                    visibility=Kudos.Visibility.TEAM,
                    target_teams__memberships__user=user,
                )
            )
            .distinct()
        )
        if self.action == "list":
            queryset = self._apply_filters(queryset, self.request.query_params)
        return queryset

    def _apply_filters(self, queryset, params):
        skill = params.get("skill")
        sender = params.get("sender")
        recipient = params.get("recipient")
        team = params.get("team")
        visibility = params.get("visibility")
        search_query = params.get("q")
        ordering = params.get("ordering", "-created_at")

        if skill:
            queryset = queryset.filter(skills__id=skill)
        if sender:
            queryset = queryset.filter(sender_id=sender)
        if recipient:
            queryset = queryset.filter(recipient_id=recipient)
        if team:
            queryset = queryset.filter(target_teams__id=team)
        if visibility in {
            Kudos.Visibility.PUBLIC,
            Kudos.Visibility.TEAM,
            Kudos.Visibility.PRIVATE,
        }:
            queryset = queryset.filter(visibility=visibility)
        if search_query:
            queryset = queryset.filter(message__icontains=search_query)
        if ordering not in {"created_at", "-created_at"}:
            ordering = "-created_at"
        return queryset.order_by(ordering).distinct()

    def get_serializer_class(self):
        if self.action in {"list", "retrieve"}:
            return KudosReadSerializer
        return KudosWriteSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        response_data = KudosReadSerializer(
            serializer.instance,
            context=self.get_serializer_context(),
        ).data
        headers = self.get_success_headers(response_data)
        return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        response_data = KudosReadSerializer(
            serializer.instance,
            context=self.get_serializer_context(),
        ).data
        return Response(response_data)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)


class PublicKudosListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = KudosReadSerializer

    def get_queryset(self):
        queryset = (
            Kudos.objects.select_related("sender", "recipient")
            .prefetch_related("skills", "target_teams")
            .filter(visibility=Kudos.Visibility.PUBLIC)
            .distinct()
        )
        skill = self.request.query_params.get("skill")
        sender = self.request.query_params.get("sender")
        recipient = self.request.query_params.get("recipient")
        team = self.request.query_params.get("team")
        search_query = self.request.query_params.get("q")
        ordering = self.request.query_params.get("ordering", "-created_at")

        if skill:
            queryset = queryset.filter(skills__id=skill)
        if sender:
            queryset = queryset.filter(sender_id=sender)
        if recipient:
            queryset = queryset.filter(recipient_id=recipient)
        if team:
            queryset = queryset.filter(target_teams__id=team)
        if search_query:
            queryset = queryset.filter(message__icontains=search_query)
        if ordering not in {"created_at", "-created_at"}:
            ordering = "-created_at"

        return queryset.order_by(ordering).distinct()
