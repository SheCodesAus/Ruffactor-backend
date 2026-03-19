import csv
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login, logout as auth_logout, update_session_auth_hash
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Kudos, KudosComment, Profile, SkillCategory, Team, TeamMembership
from .serializers import (
    ActiveTeamWriteSerializer,
    KudosCommentReadSerializer,
    KudosCommentWriteSerializer,
    KudosReadSerializer,
    KudosWriteSerializer,
    LoginSerializer,
    SignUpSerializer,
    SkillCategorySerializer,
    UserAccountPatchSerializer,
    TeamMembershipSerializer,
    TeamMembershipWriteSerializer,
    TeamSerializer,
    UserSummarySerializer
)

User = get_user_model()


def _request_prefers_html(request):
    """Return True when the request is a browser navigation or form post."""
    accept_header = request.headers.get("Accept", "")
    content_type = request.content_type or ""
    return "text/html" in accept_header or content_type == "application/x-www-form-urlencoded"


def _get_safe_next_url(request):
    """Return a safe post-login redirect target for browser flows."""
    next_url = request.data.get("next") or request.query_params.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return "/auth/profile/"


def _user_teams_queryset(user):
    """Return distinct teams that include the provided user.

    Args:
        user (User): Auth user instance.

    Returns:
        QuerySet[Team]: Alphabetically ordered teams the user belongs to.
    """
    return Team.objects.filter(memberships__user=user).order_by("name").distinct()


def _ensure_active_team(user, team):
    """Set an active team only when the user does not already have one selected."""
    profile, _ = Profile.objects.get_or_create(user=user)
    if profile.active_team_id is None and team is not None:
        profile.active_team = team
        profile.save(update_fields=["active_team", "updated_at"])


def _clear_active_team_if_removed(user, team):
    """Clear the active team when the removed membership was currently selected."""
    profile, _ = Profile.objects.get_or_create(user=user)
    if profile.active_team_id == getattr(team, "id", None):
        profile.active_team = None
        profile.save(update_fields=["active_team", "updated_at"])


def _get_profile_and_teams(user):
    """Return profile and membership teams, correcting stale active-team state.

    Args:
        user (User): Auth user instance.

    Returns:
        tuple[Profile, QuerySet[Team]]: User profile and membership teams.
    """
    profile, _ = Profile.objects.get_or_create(user=user)
    teams = _user_teams_queryset(user)
    if profile.active_team_id and not teams.filter(id=profile.active_team_id).exists():
        profile.active_team = None
        profile.save(update_fields=["active_team", "updated_at"])
    return profile, teams


def _serialize_user_payload(user):
    """Build the canonical user payload used by auth/profile endpoints.

    Args:
        user (User): User to serialize.

    Returns:
        dict: Frontend-ready user data including profile and teams.
    """
    profile, teams = _get_profile_and_teams(user)
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "display_name": profile.display_name,
        "bio": profile.bio,
        "avatar_url": profile.avatar_url,
        "active_team": TeamSerializer(profile.active_team).data if profile.active_team else None,
        "teams": TeamSerializer(teams, many=True).data,
        "snapshot": _build_kudos_snapshot(user),
    }


def _build_user_lookup_query(prefix, value):
    """Build a flexible user lookup query for sender/recipient filtering."""
    return (
        Q(**{f"{prefix}__username__icontains": value})
        | Q(**{f"{prefix}__email__icontains": value})
        | Q(**{f"{prefix}__first_name__icontains": value})
        | Q(**{f"{prefix}__last_name__icontains": value})
        | Q(**{f"{prefix}__profile__display_name__icontains": value})
    )


def _current_month_bounds():
    """Return the inclusive/exclusive datetime bounds for the current month."""
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 12:
        next_month_start = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month_start = month_start.replace(month=month_start.month + 1)
    return month_start, next_month_start


def _filter_to_current_month(queryset):
    """Limit feed querysets to kudos created during the current month."""
    month_start, next_month_start = _current_month_bounds()
    return queryset.filter(created_at__gte=month_start, created_at__lt=next_month_start)


def _build_recipient_lookup_query(value):
    """Build recipient search query covering both legacy and multi-recipient relations."""
    return _build_user_lookup_query("recipient", value) | _build_user_lookup_query(
        "recipients",
        value,
    )


def _build_kudos_snapshot(user):
    """Return aggregate kudos counts for the authenticated user's dashboard snapshot."""
    return {
        "kudos_given": Kudos.objects.filter(sender=user, is_archived=False).count(),
        "kudos_received": (
            Kudos.objects.filter(
                Q(recipient=user) | Q(recipients=user),
                is_archived=False,
            )
            .distinct()
            .count()
        ),
    }


def _visible_kudos_queryset(user):
    """Return kudos visible to the requesting user using feed visibility rules."""
    queryset = (
        Kudos.objects.select_related("sender", "recipient")
        .prefetch_related("recipients", "skills", "target_teams", "approved_by", "archived_by")
    )
    if user.is_staff:
        return queryset
    return queryset.filter(
        Q(visibility=Kudos.Visibility.PUBLIC)
        | Q(sender=user)
        | Q(recipient=user)
        | Q(recipients=user)
        | Q(
            visibility=Kudos.Visibility.TEAM,
            target_teams__memberships__user=user,
        )
    ).filter(is_archived=False).distinct()


def _apply_kudos_filters(queryset, params):
    """Apply shared kudos list filters used by authenticated feed endpoints."""
    # List endpoint query params supported by frontend:
    # skill, sender, recipient, team, visibility, approved, archived, q, ordering
    queryset = _filter_to_current_month(queryset)
    skill = params.get("skill")
    sender = params.get("sender")
    recipient = params.get("recipient")
    team = params.get("team")
    visibility = params.get("visibility")
    approved = params.get("approved")
    archived = params.get("archived")
    search_query = params.get("q")
    ordering = params.get("ordering", "-created_at")

    if skill:
        queryset = queryset.filter(skills__id=skill)
    if sender:
        if sender.isdigit():
            queryset = queryset.filter(sender_id=sender)
        else:
            queryset = queryset.filter(_build_user_lookup_query("sender", sender))
    if recipient:
        if recipient.isdigit():
            queryset = queryset.filter(Q(recipient_id=recipient) | Q(recipients__id=recipient))
        else:
            queryset = queryset.filter(_build_recipient_lookup_query(recipient))
    if team:
        queryset = queryset.filter(target_teams__id=team)
    if visibility in {
        Kudos.Visibility.PUBLIC,
        Kudos.Visibility.TEAM,
        Kudos.Visibility.PRIVATE,
    }:
        queryset = queryset.filter(visibility=visibility)
    if approved in {"true", "false"}:
        queryset = queryset.filter(is_approved=(approved == "true"))
    if archived in {"true", "false"}:
        queryset = queryset.filter(is_archived=(archived == "true"))
    if search_query:
        queryset = queryset.filter(
            Q(message__icontains=search_query)
            | _build_user_lookup_query("sender", search_query)
            | _build_recipient_lookup_query(search_query)
        )
    if ordering not in {"created_at", "-created_at"}:
        ordering = "-created_at"
    return queryset.order_by(ordering).distinct()


class SignUpView(generics.CreateAPIView):
    serializer_class = SignUpSerializer
    permission_classes = [permissions.IsAuthenticated]


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        """Render a simple backend login page for browser redirects."""
        next_url = _get_safe_next_url(request)
        if request.user.is_authenticated:
            return redirect(next_url)
        return render(
            request,
            "accounts/login.html",
            {
                "next": next_url,
            },
        )

    def post(self, request):
        """Authenticate user and return token plus hydrated user payload.

        Args:
            request (Request): DRF request containing `email`, `password`, and optional
                `team_id`.

        Returns:
            Response: 200 response with auth token and serialized user data.
        """
        serializer = LoginSerializer(data=request.data)
        if _request_prefers_html(request):
            if not serializer.is_valid():
                return render(
                    request,
                    "accounts/login.html",
                    {
                        "next": _get_safe_next_url(request),
                        "error": "Invalid email or password.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        auth_login(request, user)
        profile, _ = _get_profile_and_teams(user)
        if "team" in serializer.validated_data:
            profile.active_team = serializer.validated_data["team"]
            profile.save(update_fields=["active_team", "updated_at"])
        token, _ = Token.objects.get_or_create(user=user)
        next_url = _get_safe_next_url(request)

        if _request_prefers_html(request):
            response = redirect(next_url)
            response.set_cookie(
                "auth_token",
                token.key,
                httponly=True,
                samesite="Lax",
                secure=not settings.DEBUG,
            )
            return response

        return Response(
            {
                "message": "Login successful.",
                "token": token.key,
                "user": _serialize_user_payload(user),
            },
            status=status.HTTP_200_OK,
        )


class UserAccountView(APIView):
    """`/auth/user/` endpoint for create (POST), self update (PATCH), self delete (DELETE)."""

    def get_permissions(self):
        """Choose permission set based on method.

        Returns:
            list[BasePermission]: `IsAuthenticated` for all methods.
        """
        return [permissions.IsAuthenticated()]

    def post(self, request):
        """Create a user account through the signup serializer.

        Args:
            request (Request): DRF request containing signup payload.

        Returns:
            Response: 201 response with created user payload.
        """
        serializer = SignUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "message": "User created.",
                "user": _serialize_user_payload(user),
            },
            status=status.HTTP_201_CREATED,
        )

    def patch(self, request):
        """Partially update authenticated user data.

        Args:
            request (Request): DRF request containing mutable user fields.

        Returns:
            Response: 200 response with updated user payload.
        """
        serializer = UserAccountPatchSerializer(
            instance=request.user,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        if "password" in serializer.validated_data:
            update_session_auth_hash(request, user)
        return Response(
            {
                "message": "User updated.",
                "user": _serialize_user_payload(user),
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request):
        """Delete authenticated user when no protected relations block deletion.

        Args:
            request (Request): DRF request.

        Returns:
            Response: 204 when deleted, 409 when protected by related records.
        """
        user = request.user
        try:
            user.delete()
        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "Cannot delete user because related kudos records exist. "
                        "Contact an administrator."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        auth_logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)

class UserListView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get(self, request):
        users = User.objects.all().order_by("id")
        serializer = UserSummarySerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Return authenticated user's profile payload.

        Args:
            request (Request): DRF request for current user.

        Returns:
            Response: 200 response containing serialized current user.
        """
        return Response(_serialize_user_payload(request.user), status=status.HTTP_200_OK)


class ActiveTeamView(APIView):
    """`/auth/active-team/` endpoint to read/update the logged-in user's active team."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Return current active team and selectable teams for the user.

        Args:
            request (Request): DRF request for current user.

        Returns:
            Response: Active team object (or null) and membership team list.
        """
        profile, teams = _get_profile_and_teams(request.user)
        return Response(
            {
                "active_team": (
                    TeamSerializer(profile.active_team).data
                    if profile.active_team
                    else None
                ),
                "teams": TeamSerializer(teams, many=True).data,
            }
        )

    def put(self, request):
        """Set or clear authenticated user's active team.

        Args:
            request (Request): DRF request containing `team_id` (or null).

        Returns:
            Response: Updated active team and membership team list.
        """
        serializer = ActiveTeamWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        profile, teams = _get_profile_and_teams(request.user)
        profile.active_team = serializer.validated_data["team"]
        profile.save(update_fields=["active_team", "updated_at"])
        return Response(
            {
                "active_team": (
                    TeamSerializer(profile.active_team).data
                    if profile.active_team
                    else None
                ),
                "teams": TeamSerializer(teams, many=True).data,
            }
        )

    def patch(self, request):
        """Support PATCH by delegating to PUT active-team implementation.

        Args:
            request (Request): DRF request containing `team_id` (or null).

        Returns:
            Response: Updated active team payload.
        """
        return self.put(request)


class IsSenderOrStaff(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        """Evaluate object-level write permission for kudos operations.

        Args:
            request (Request): Incoming request.
            view (APIView): Current view/viewset.
            obj (Kudos): Target kudos object.

        Returns:
            bool: `True` for safe reads, comment actions, sender writes, and staff.
        """
        if getattr(view, "action", None) in {"comments", "comment_detail"}:
            return True
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_staff or obj.sender_id == request.user.id


class TeamViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Team list/create + membership management actions used by frontend team selectors."""

    serializer_class = TeamSerializer
    queryset = Team.objects.all()

    def get_permissions(self):
        """Resolve team viewset permissions per action.

        Returns:
            list[BasePermission]: Admin-only permission for create, authenticated
                permission otherwise.
        """
        if self.action == "create":
            return [permissions.IsAuthenticated(), permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        """Return action queryset scoped by requester role.

        Returns:
            QuerySet[Team]: All teams for staff; membership teams for non-staff.
        """
        if self.request.user.is_staff:
            return Team.objects.all()
        return Team.objects.filter(memberships__user=self.request.user).distinct()

    def perform_create(self, serializer):
        """Persist new team and auto-create creator admin membership.

        Args:
            serializer (TeamSerializer): Validated serializer for create action.
        """
        team = serializer.save()
        membership, created = TeamMembership.objects.get_or_create(
            team=team,
            user=self.request.user,
            defaults={"role": TeamMembership.Role.ADMIN},
        )
        if created and membership.role == TeamMembership.Role.ADMIN:
            _ensure_active_team(self.request.user, team)

    def _assert_team_admin_or_staff(self, team):
        """Validate that requester can manage memberships for the team.

        Args:
            team (Team): Team targeted for membership mutation.

        Raises:
            PermissionDenied: If requester is neither staff nor team admin.
        """
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
        """Add or update a team membership record.

        Args:
            request (Request): Request containing `user_id` and optional `role`.
            pk (str | None): Team primary key from route.

        Returns:
            Response: Membership payload with 201 (created) or 200 (updated).
        """
        team = get_object_or_404(Team, pk=pk)
        self._assert_team_admin_or_staff(team)
        serializer = TeamMembershipWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        membership, created = TeamMembership.objects.update_or_create(
            team=team,
            user=serializer.validated_data["user"],
            defaults={"role": serializer.validated_data["role"]},
        )
        if created:
            _ensure_active_team(serializer.validated_data["user"], team)
        response_serializer = TeamMembershipSerializer(membership)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @add_member.mapping.delete
    def remove_member(self, request, pk=None):
        """Remove team membership using `user_id` query parameter.

        Args:
            request (Request): Request containing `user_id` in query params.
            pk (str | None): Team primary key from route.

        Returns:
            Response: 204 when removed, 400 when `user_id` missing, 404 when not found.
        """
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
        _clear_active_team_if_removed(membership.user, team)
        membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"members/(?P<user_id>[^/.]+)",
    )
    def remove_member_by_path(self, request, pk=None, user_id=None):
        """Remove team membership using `user_id` route segment.

        Args:
            request (Request): Incoming DRF request.
            pk (str | None): Team primary key from route.
            user_id (str | None): User identifier from route.

        Returns:
            Response: 204 when removed or 404 when membership does not exist.
        """
        team = get_object_or_404(Team, pk=pk)
        self._assert_team_admin_or_staff(team)
        membership = TeamMembership.objects.filter(team=team, user_id=user_id).first()
        if not membership:
            return Response(status=status.HTTP_404_NOT_FOUND)
        _clear_active_team_if_removed(membership.user, team)
        membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SkillCategoryViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Skill catalog endpoint. Frontend should use GET list for predefined skill tags."""

    serializer_class = SkillCategorySerializer
    queryset = SkillCategory.objects.all()

    def get_permissions(self):
        """Resolve skill viewset permissions per action.

        Returns:
            list[BasePermission]: Admin-only permission for create, authenticated
                permission otherwise.
        """
        if self.action == "create":
            return [permissions.IsAuthenticated(), permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        """Return queryset for skills according to action semantics.

        Returns:
            QuerySet[SkillCategory]: Active skills for list, full queryset otherwise.
        """
        if self.action == "list":
            return SkillCategory.objects.filter(is_active=True)
        return SkillCategory.objects.all()


class ReceivedKudosByUserView(generics.ListAPIView):
    """Return kudos received by a specific user, scoped by requester visibility."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = KudosReadSerializer

    def get_queryset(self):
        user = get_object_or_404(User, pk=self.kwargs["pk"])
        return (
            _visible_kudos_queryset(self.request.user)
            .filter(Q(recipient=user) | Q(recipients=user))
            .order_by("-created_at")
            .distinct()
        )


class GivenKudosByUserView(generics.ListAPIView):
    """Return kudos given by a specific user, scoped by requester visibility."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = KudosReadSerializer

    def get_queryset(self):
        user = get_object_or_404(User, pk=self.kwargs["pk"])
        return _visible_kudos_queryset(self.request.user).filter(sender=user).order_by(
            "-created_at"
        )


class KudosViewSet(viewsets.ModelViewSet):
    """Main kudos CRUD + comments + admin moderation actions."""

    permission_classes = [permissions.IsAuthenticated, IsSenderOrStaff]

    def _assert_staff(self):
        """Assert requester is staff before admin-only kudos actions.

        Raises:
            PermissionDenied: If requester is not a staff user.
        """
        if not self.request.user.is_staff:
            raise PermissionDenied("Only administrators can perform this action.")

    def get_queryset(self):
        """Build kudos queryset scoped by visibility, role, and action.

        Returns:
            QuerySet[Kudos]: Queryset visible to requester and optionally filter-applied.
        """
        user = self.request.user
        filtered = _visible_kudos_queryset(user)
        if self.action == "list":
            filtered = self._apply_filters(filtered, self.request.query_params)
        return filtered

    def _apply_filters(self, queryset, params):
        """Apply supported query-parameter filters to kudos queryset.

        Args:
            queryset (QuerySet[Kudos]): Base queryset before filter application.
            params (QueryDict): Incoming request query parameters.

        Returns:
            QuerySet[Kudos]: Filtered and ordered queryset.
        """
        return _apply_kudos_filters(queryset, params)

    def get_serializer_class(self):
        """Select serializer class based on action read/write behavior.

        Returns:
            type[Serializer]: `KudosReadSerializer` for list/retrieve, otherwise
                `KudosWriteSerializer`.
        """
        if self.action in {"list", "retrieve"}:
            return KudosReadSerializer
        return KudosWriteSerializer

    def create(self, request, *args, **kwargs):
        """Create kudos and respond using read serializer shape.

        Args:
            request (Request): Request containing create payload.
            *args: DRF positional args.
            **kwargs: DRF keyword args.

        Returns:
            Response: 201 response with hydrated kudos payload.
        """
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
        """Update or replace kudos with archive restrictions for non-staff users.

        Args:
            request (Request): Request containing update payload.
            *args: DRF positional args.
            **kwargs: DRF keyword args; may include `partial`.

        Returns:
            Response: 200 response with updated kudos payload.

        Raises:
            PermissionDenied: If non-staff attempts to edit archived kudos.
        """
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        if instance.is_archived and not request.user.is_staff:
            raise PermissionDenied("Archived kudos can only be edited by administrators.")
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        response_data = KudosReadSerializer(
            serializer.instance,
            context=self.get_serializer_context(),
        ).data
        return Response(response_data)

    def partial_update(self, request, *args, **kwargs):
        """Handle PATCH by delegating to `update` with partial behavior enabled.

        Args:
            request (Request): Request containing partial update payload.
            *args: DRF positional args.
            **kwargs: DRF keyword args.

        Returns:
            Response: Same as `update`.
        """
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @action(detail=False, methods=["get"], url_path="snapshot")
    def snapshot(self, request):
        """Return home-dashboard aggregate kudos counts for the current user."""
        return Response(_build_kudos_snapshot(request.user), status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        """Approve a kudos item and persist approval audit fields.

        Args:
            request (Request): Request from authenticated staff user.
            pk (str | None): Kudos primary key.

        Returns:
            Response: 200 response with updated kudos payload.
        """
        self._assert_staff()
        kudos = self.get_object()
        kudos.is_approved = True
        kudos.approved_at = timezone.now()
        kudos.approved_by = request.user
        kudos.save(update_fields=["is_approved", "approved_at", "approved_by", "updated_at"])
        return Response(
            KudosReadSerializer(kudos, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request, pk=None):
        """Archive kudos and persist archive audit fields.

        Args:
            request (Request): Request from authenticated staff user.
            pk (str | None): Kudos primary key.

        Returns:
            Response: 200 response with updated kudos payload.
        """
        self._assert_staff()
        kudos = self.get_object()
        kudos.is_archived = True
        kudos.archived_at = timezone.now()
        kudos.archived_by = request.user
        kudos.save(update_fields=["is_archived", "archived_at", "archived_by", "updated_at"])
        return Response(
            KudosReadSerializer(kudos, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="unarchive")
    def unarchive(self, request, pk=None):
        """Unarchive kudos and clear archive audit fields.

        Args:
            request (Request): Request from authenticated staff user.
            pk (str | None): Kudos primary key.

        Returns:
            Response: 200 response with updated kudos payload.
        """
        self._assert_staff()
        kudos = self.get_object()
        kudos.is_archived = False
        kudos.archived_at = None
        kudos.archived_by = None
        kudos.save(update_fields=["is_archived", "archived_at", "archived_by", "updated_at"])
        return Response(
            KudosReadSerializer(kudos, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        """Export filtered kudos list as CSV (admin only).

        Args:
            request (Request): Request containing optional list filters.

        Returns:
            HttpResponse: CSV download response.
        """
        self._assert_staff()
        queryset = self._apply_filters(self.get_queryset(), request.query_params)

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="kudos_export.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "id",
                "sender",
                "recipients",
                "message",
                "visibility",
                "link_url",
                "media_url",
                "skill_slugs",
                "is_approved",
                "approved_at",
                "approved_by",
                "is_archived",
                "archived_at",
                "archived_by",
                "created_at",
            ]
        )
        for kudos in queryset:
            recipient_usernames = list(kudos.recipients.values_list("username", flat=True))
            if not recipient_usernames and kudos.recipient_id:
                recipient_usernames = [kudos.recipient.username]
            writer.writerow(
                [
                    kudos.id,
                    kudos.sender.username,
                    "|".join(recipient_usernames),
                    kudos.message,
                    kudos.visibility,
                    kudos.link_url,
                    kudos.media_url,
                    "|".join(kudos.skills.values_list("slug", flat=True)),
                    kudos.is_approved,
                    kudos.approved_at.isoformat() if kudos.approved_at else "",
                    kudos.approved_by.username if kudos.approved_by else "",
                    kudos.is_archived,
                    kudos.archived_at.isoformat() if kudos.archived_at else "",
                    kudos.archived_by.username if kudos.archived_by else "",
                    kudos.created_at.isoformat(),
                ]
            )
        return response

    @action(detail=True, methods=["get", "post"], url_path="comments")
    def comments(self, request, pk=None):
        """List comments or create a comment on a specific kudos item.

        Args:
            request (Request): GET for list, POST with `body` for create.
            pk (str | None): Kudos primary key.

        Returns:
            Response: Comment list (200) or created comment payload (201).
        """
        kudos = self.get_object()
        if request.method == "GET":
            queryset = kudos.comments.select_related("author").all()
            serializer = KudosCommentReadSerializer(queryset, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = KudosCommentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(kudos=kudos, author=request.user)
        return Response(KudosCommentReadSerializer(comment).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["patch", "delete"],
        url_path=r"comments/(?P<comment_id>[^/.]+)",
    )
    def comment_detail(self, request, pk=None, comment_id=None):
        """Update or delete one comment under a kudos item.

        Args:
            request (Request): PATCH with `body` or DELETE request.
            pk (str | None): Kudos primary key.
            comment_id (str | None): Comment primary key.

        Returns:
            Response: Updated payload (200) or empty delete response (204).

        Raises:
            PermissionDenied: If requester is neither comment author nor staff.
        """
        kudos = self.get_object()
        comment = get_object_or_404(KudosComment, pk=comment_id, kudos=kudos)

        if not request.user.is_staff and comment.author_id != request.user.id:
            raise PermissionDenied("Only the comment author or staff can modify comments.")

        if request.method == "DELETE":
            comment.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = KudosCommentWriteSerializer(comment, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(KudosCommentReadSerializer(comment).data, status=status.HTTP_200_OK)


class PublicKudosListView(generics.ListAPIView):
    """Read-only kudos feed that now requires authentication."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = KudosReadSerializer

    def get_queryset(self):
        """Build public feed queryset with optional filters and ordering.

        Returns:
            QuerySet[Kudos]: Public, non-archived kudos ordered by recency by default.
        """
        queryset = (
            Kudos.objects.select_related("sender", "recipient")
            .prefetch_related("recipients", "skills", "target_teams")
            .filter(visibility=Kudos.Visibility.PUBLIC, is_archived=False)
            .distinct()
        )
        return _apply_kudos_filters(queryset, self.request.query_params)
