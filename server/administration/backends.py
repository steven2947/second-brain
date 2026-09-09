"""只允许后台显式调用密码认证，普通 authenticate 不触发此后端。"""
from django.contrib.auth.backends import ModelBackend


class AdminBackend(ModelBackend):
    """后台专用密码认证与 active staff 会话恢复，MFA 权限由服务层核验。"""
    def authenticate(self, request, username=None, password=None, *, admin_login=False, **kwargs):
        """仅在管理员登录服务显式指定时校验密码；不会给普通登录补认证。"""
        if not admin_login:
            return None
        user = super().authenticate(request, username=username, password=password, **kwargs)
        return user if user and user.is_staff else None

    def get_user(self, user_id):
        """每次会话恢复都检查当前账号状态和 staff 标志。"""
        user = super().get_user(user_id)
        return user if user and user.is_staff else None
