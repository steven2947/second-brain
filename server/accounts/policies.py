"""本机账号功能测试说明集中定义；并非已经法律审核的正式运营政策。"""
from django.conf import settings

from .serializers import AuthOptionsSerializer, RegistrationSerializer


TEST_POLICIES = {
    "terms": {
        "title": "本机功能测试使用说明（非正式运营条款）",
        "body": "本项目当前仅供本机功能测试，需要测试邀请才能注册。模型尚未接通，不能承诺提供问题分析或建议。没有真实邮件验证；密码找回默认关闭，显式启用本机捕获时只保存私有测试邮件，不代表真实邮件送达，SMTP需由部署者单独配置。请使用测试账号，不要输入真实敏感资料。这是测试说明，未经法律审核；正式运营政策待负责人审核后另行提供。版本更新后需要重新阅读并明确同意，不会自动代替你同意新版本。",
    },
    "privacy": {
        "title": "本机功能测试数据说明（非正式隐私政策）",
        "body": "本机功能测试会将你填写的邮箱、昵称以及密码哈希存入本项目数据库，同时记录你明确接受的测试说明版本和时间。密码以哈希形式保存，不保存明文密码；登录使用服务端会话。尚无真实邮件验证；密码找回待发记录不保存邮箱和令牌，本机捕获会在私有文件中保存收件邮箱及30分钟有效的重置链接，由隐私维护清理，注销时撤销。不要输入真实敏感资料；请使用仅用于本机测试的数据。本说明未经法律审核，正式运营政策待负责人审核，不能代表正式服务的数据处理承诺。",
    },
}


def auth_options():
    """无参数；仅从已实现能力和实际注册字段构建匿名公开信息。"""
    from .password_reset import reset_options
    versions = settings.ACCOUNT_POLICY_VERSIONS
    password = RegistrationSerializer().fields["password"]
    return AuthOptionsSerializer({
        "registration": {
            "enabled": settings.SB_ENV == "development",
            "invitation_required": True,
            "policy_versions": dict(versions),
            "policies": [{"kind": kind, "version": versions[kind], **TEST_POLICIES[kind], "test_only": True}
                         for kind in ("terms", "privacy")],
        },
        "password": {"min_length": password.min_length, "max_length": password.max_length},
        "password_reset": reset_options(),
        "admin_mfa": {"available": True},
    }).data
