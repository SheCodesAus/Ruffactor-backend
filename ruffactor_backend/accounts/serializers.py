from django.contrib.auth import authenticate, get_user_model, password_validation
from django.utils.text import slugify
from rest_framework import serializers

from .models import Kudos, Profile, SkillCategory, Team, TeamMembership


User = get_user_model()


class SignUpSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "password",
            "confirm_password",
        )
        read_only_fields = ("id",)

    def validate_email(self, value):
        normalized = value.strip().lower()

        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return normalized

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})

        temp_user = User(
            username=attrs.get("username"),
            email=attrs.get("email"),
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        password_validation.validate_password(attrs["password"], user=temp_user)
        return attrs

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        Profile.objects.get_or_create(user=user)
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    team_id = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(),
        source="team",
        required=False,
        allow_null=True,
    )

    def validate(self, attrs):
        email = attrs.get("email").strip().lower()
        password = attrs.get("password")

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid email or password.")

        user = authenticate(username=user.username, password=password)
        if not user:
            raise serializers.ValidationError("Invalid email or password.")

        selected_team = attrs.get("team")
        if selected_team is not None:
            is_member = TeamMembership.objects.filter(user=user, team=selected_team).exists()
            if not is_member:
                raise serializers.ValidationError(
                    {"team_id": "You can only select teams you belong to."}
                )

        attrs["user"] = user
        return attrs


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "first_name", "last_name")


class TeamSerializer(serializers.ModelSerializer):
    slug = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Team
        fields = ("id", "name", "slug", "description", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def _next_unique_slug(self, base_slug, instance=None):
        slug = base_slug or "team"
        candidate = slug
        index = 2
        queryset = Team.objects.all()
        if instance is not None:
            queryset = queryset.exclude(pk=instance.pk)
        while queryset.filter(slug=candidate).exists():
            candidate = f"{slug}-{index}"
            index += 1
        return candidate

    def validate(self, attrs):
        if self.instance is not None:
            if "slug" in attrs and attrs["slug"] == "":
                name = attrs.get("name", self.instance.name)
                attrs["slug"] = self._next_unique_slug(slugify(name), instance=self.instance)
            elif "name" in attrs and "slug" not in attrs:
                attrs["slug"] = self._next_unique_slug(
                    slugify(attrs["name"]),
                    instance=self.instance,
                )
            return attrs

        name = attrs.get("name", "")
        raw_slug = attrs.get("slug")
        if raw_slug in (None, ""):
            attrs["slug"] = self._next_unique_slug(slugify(name))
        return attrs


class TeamMembershipSerializer(serializers.ModelSerializer):
    user = UserSummarySerializer(read_only=True)

    class Meta:
        model = TeamMembership
        fields = ("id", "user", "role", "created_at")
        read_only_fields = ("id", "created_at")


class TeamMembershipWriteSerializer(serializers.Serializer):
    user_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), source="user")
    role = serializers.ChoiceField(
        choices=TeamMembership.Role.choices,
        default=TeamMembership.Role.MEMBER,
    )


class ActiveTeamWriteSerializer(serializers.Serializer):
    team_id = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(),
        source="team",
        allow_null=True,
    )

    def validate_team(self, value):
        if value is None:
            return value
        user = self.context["request"].user
        is_member = TeamMembership.objects.filter(user=user, team=value).exists()
        if not is_member:
            raise serializers.ValidationError("You can only select teams you belong to.")
        return value


class SkillCategorySerializer(serializers.ModelSerializer):
    slug = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = SkillCategory
        fields = ("id", "name", "slug", "description", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def _next_unique_slug(self, base_slug, instance=None):
        slug = base_slug or "skill"
        candidate = slug
        index = 2
        queryset = SkillCategory.objects.all()
        if instance is not None:
            queryset = queryset.exclude(pk=instance.pk)
        while queryset.filter(slug=candidate).exists():
            candidate = f"{slug}-{index}"
            index += 1
        return candidate

    def validate(self, attrs):
        if self.instance is not None:
            if "slug" in attrs and attrs["slug"] == "":
                name = attrs.get("name", self.instance.name)
                attrs["slug"] = self._next_unique_slug(slugify(name), instance=self.instance)
            elif "name" in attrs and "slug" not in attrs:
                attrs["slug"] = self._next_unique_slug(
                    slugify(attrs["name"]),
                    instance=self.instance,
                )
            return attrs

        name = attrs.get("name", "")
        raw_slug = attrs.get("slug")
        if raw_slug in (None, ""):
            attrs["slug"] = self._next_unique_slug(slugify(name))
        return attrs


class KudosReadSerializer(serializers.ModelSerializer):
    sender = UserSummarySerializer(read_only=True)
    recipient = UserSummarySerializer(read_only=True)
    skills = SkillCategorySerializer(many=True, read_only=True)
    target_teams = TeamSerializer(many=True, read_only=True)

    class Meta:
        model = Kudos
        fields = (
            "id",
            "sender",
            "recipient",
            "message",
            "link_url",
            "media_url",
            "visibility",
            "skills",
            "target_teams",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class KudosWriteSerializer(serializers.ModelSerializer):
    skill_ids = serializers.PrimaryKeyRelatedField(
        queryset=SkillCategory.objects.filter(is_active=True),
        many=True,
        required=False,
        write_only=True,
    )
    target_team_ids = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(),
        many=True,
        required=False,
        write_only=True,
    )

    class Meta:
        model = Kudos
        fields = (
            "id",
            "recipient",
            "message",
            "link_url",
            "media_url",
            "visibility",
            "skill_ids",
            "target_team_ids",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user
        instance = self.instance

        visibility = attrs.get(
            "visibility",
            getattr(instance, "visibility", Kudos.Visibility.PUBLIC),
        )
        teams = attrs.get("target_team_ids")
        if teams is None and instance is not None:
            teams = list(instance.target_teams.all())
        elif teams is None:
            teams = []

        if visibility == Kudos.Visibility.TEAM and not teams:
            raise serializers.ValidationError(
                {"target_team_ids": "Team visibility requires at least one team."}
            )

        if visibility != Kudos.Visibility.TEAM and teams:
            raise serializers.ValidationError(
                {"target_team_ids": "target_team_ids must be empty unless visibility is team."}
            )

        if visibility == Kudos.Visibility.TEAM and not user.is_staff:
            team_ids = [team.id for team in teams]
            memberships = set(
                TeamMembership.objects.filter(
                    user=user,
                    team_id__in=team_ids,
                ).values_list("team_id", flat=True)
            )
            if memberships != set(team_ids):
                raise serializers.ValidationError(
                    {"target_team_ids": "You must belong to all targeted teams."}
                )

        recipient = attrs.get("recipient", getattr(instance, "recipient", None))
        if recipient is not None and recipient == user:
            raise serializers.ValidationError({"recipient": "Sender cannot be recipient."})

        return attrs

    def create(self, validated_data):
        skill_ids = validated_data.pop("skill_ids", [])
        target_team_ids = validated_data.pop("target_team_ids", [])
        kudos = Kudos.objects.create(sender=self.context["request"].user, **validated_data)
        kudos.skills.set(skill_ids)
        kudos.target_teams.set(target_team_ids)
        return kudos

    def update(self, instance, validated_data):
        skill_ids = validated_data.pop("skill_ids", None)
        target_team_ids = validated_data.pop("target_team_ids", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if skill_ids is not None:
            instance.skills.set(skill_ids)
        if target_team_ids is not None:
            instance.target_teams.set(target_team_ids)

        return instance
