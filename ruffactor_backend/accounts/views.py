from rest_framework import generics, permissions

from .serializers import SignUpSerializer


class SignUpView(generics.CreateAPIView):
    serializer_class = SignUpSerializer
    permission_classes = [permissions.AllowAny]
