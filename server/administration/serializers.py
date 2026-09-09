"""后台身份端点显式输入与最小身份返回。"""
from rest_framework import serializers
from accounts.serializers import StrictSerializer
from .permissions import PERMISSIONS


class AdminReauthSerializer(StrictSerializer):
    password = serializers.CharField(max_length=256, trim_whitespace=False, write_only=True)
    token = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    method = serializers.ChoiceField(choices=['totp', 'recovery'])


class AdminLoginSerializer(AdminReauthSerializer):
    email = serializers.EmailField(max_length=254)


class PublicAdministratorSerializer(StrictSerializer):
    id = serializers.UUIDField()
    email = serializers.EmailField(max_length=254)
    display_name = serializers.CharField(max_length=80)


class AdminIdentitySerializer(StrictSerializer):
    user = PublicAdministratorSerializer()
    granted_permissions = serializers.ListField(child=serializers.ChoiceField(choices=PERMISSIONS))
    verified_at = serializers.DateTimeField(format=None)
    fresh_until = serializers.DateTimeField(format=None)
    session_expires_at = serializers.DateTimeField(format=None)
