"""沿用 Django 密码和权限后端；MFA 未实现时高权限账号不得恢复完整会话。"""
from django.contrib.auth.backends import ModelBackend


class AccountBackend(ModelBackend):
    """认证密码沿用框架，恢复 cookie 会话附加管理员 MFA 失败关闭。"""

    def get_user(self, user_id):
        """user_id 为服务端 session 内 UUID；每次读取当前状态与管理权限。"""
        user = super().get_user(user_id)
        return user if user and not (user.is_staff or user.is_superuser) else None
