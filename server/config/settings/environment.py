"""只解析调用者传入的环境，不读取本机文件、不连接数据库或模型。"""

import ipaddress
import re
import secrets
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit


class ConfigurationError(ValueError):
    """配置损坏；消息只包含字段名和固定说明，不包含配置值。"""


def required(env, key):
    """从 env 字典读取非空 key 字段，缺失时给出安全错误。"""
    value = env.get(key, "").strip()
    if not value:
        raise ConfigurationError(f"{key} 必须显式配置")
    return value


def example_secret(value):
    """判断 value 是否带有常见示例凭据标记。"""
    compact = re.sub(r"[^a-z0-9]", "", value.lower())
    return any(marker in compact for marker in (
        "changeme", "replaceme", "yourapikey", "yoursecret", "example",
        "djangoinsecure", "placeholder",
    )) or compact in {"password", "secret", "test", "postgres"}


def valid_host(value):
    """检查 value 是精确 DNS 主机名或 IP；不接受通配符、端口与 URL。"""
    try:
        ipaddress.ip_address(value[1:-1] if value.startswith("[") and value.endswith("]") else value)
        return True
    except ValueError:
        return len(value) <= 253 and all(
            re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
            for label in value.split(".")
        )


def parse_url(value, key):
    """解析 value 为 URL；key 用于生成不回显敏感数据的错误。"""
    try:
        if any(character.isspace() or ord(character) < 32 for character in value):
            raise ValueError
        parsed = urlsplit(value)
        if not parsed.hostname or not valid_host(parsed.hostname) or parsed.port == 0:
            raise ValueError
        return parsed
    except ValueError:
        raise ConfigurationError(f"{key} URL 格式无效") from None


def database_settings(value, key, production):
    """将 value PostgreSQL URL 转为连接配置；key 定位错误，production 拒绝示例密码。"""
    parsed = parse_url(value, key)
    if (parsed.scheme not in {"postgres", "postgresql"} or not parsed.username
            or not parsed.password or not parsed.path.startswith("/")
            or not parsed.path[1:] or "/" in parsed.path[1:] or parsed.fragment):
        raise ConfigurationError(f"{key} 必须是含独立账号、密码和数据库名的 PostgreSQL URL")
    username, password, database_name = (
        unquote(part) for part in (parsed.username, parsed.password, parsed.path[1:])
    )
    if any(
        unicodedata.category(character) == "Cc"
        for part in (username, password, database_name)
        for character in part
    ) or "/" in database_name:
        raise ConfigurationError(f"{key} 解码后不得含控制字符，数据库名不得含斜杠")
    if production and example_secret(password):
        raise ConfigurationError(f"{key} 不得使用示例密码")
    try:
        pairs = parse_qsl(parsed.query, strict_parsing=True)
    except ValueError:
        raise ConfigurationError(f"{key} 查询参数无效") from None
    options = {"connect_timeout": 3}
    for name, option in pairs:
        if name != "sslmode" or name in options or option not in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
            raise ConfigurationError(f"{key} 仅允许唯一 sslmode 参数")
        options[name] = option
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": database_name, "USER": username,
        "PASSWORD": password, "HOST": parsed.hostname, "PORT": parsed.port or 5432,
        "OPTIONS": options, "CONN_MAX_AGE": 0,
    }


def private_path(env, key, production, default):
    """验证 env 中 key 是私有绝对目录；production 强制指定，default 为开发默认目录。"""
    value = required(env, key) if production else env.get(key, str(default))
    path = Path(value)
    if not path.is_absolute():
        raise ConfigurationError(f"{key} 必须是私有绝对目录")
    path = path.resolve()
    if path == Path("/") or any(part.lower() in {"public", "static", "web"} for part in path.parts):
        raise ConfigurationError(f"{key} 不得指向根目录或 Web 公共目录")
    return path


def mail_settings(env, production):
    """env为显式邮件配置；production禁用本机捕获，SMTP缺项或TLS冲突时拒绝启动。"""
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email
    mode = env.get('SB_MAIL_MODE', 'disabled')
    if mode not in {'disabled', 'local_capture', 'smtp'} or (production and mode == 'local_capture'):
        raise ConfigurationError('SB_MAIL_MODE无效；生产禁止local_capture')
    result = {'SB_MAIL_MODE': mode, 'PASSWORD_RESET_TIMEOUT': 1800}
    if mode != 'smtp':
        return result
    host = required(env, 'SB_SMTP_HOST')
    if not valid_host(host):
        raise ConfigurationError('SB_SMTP_HOST必须为精确主机名')
    try:
        port = int(required(env, 'SB_SMTP_PORT'))
        timeout = float(env.get('SB_SMTP_TIMEOUT_SECONDS', '5'))
        if not 1 <= port <= 65535 or not 1 <= timeout <= 10:
            raise ValueError
    except ValueError:
        raise ConfigurationError('SMTP端口或超时无效') from None
    flags = [required(env, name).lower() for name in ('SB_SMTP_USE_TLS', 'SB_SMTP_USE_SSL')]
    if any(value not in {'true', 'false'} for value in flags) or flags.count('true') != 1:
        raise ConfigurationError('SMTP必须显式且仅启用一种TLS/SSL')
    sender = required(env, 'SB_SMTP_FROM_EMAIL')
    try:
        validate_email(sender)
        if '\r' in sender or '\n' in sender:
            raise ValidationError('invalid')
    except ValidationError:
        raise ConfigurationError('SB_SMTP_FROM_EMAIL必须为合法单一邮箱') from None
    return {**result, 'EMAIL_BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
        'EMAIL_HOST': host, 'EMAIL_PORT': port, 'EMAIL_TIMEOUT': timeout,
        'EMAIL_HOST_USER': required(env, 'SB_SMTP_USER'),
        'EMAIL_HOST_PASSWORD': required(env, 'SB_SMTP_PASSWORD'),
        'EMAIL_USE_TLS': flags[0] == 'true', 'EMAIL_USE_SSL': flags[1] == 'true',
        'DEFAULT_FROM_EMAIL': sender}


def build_settings(env):
    """根据 env 映射生成 Django 设置；失败关闭且绝不自动读取其他凭据来源。"""
    environment = env.get("SB_ENV", "development")
    if environment not in {"development", "production"}:
        raise ConfigurationError("SB_ENV 仅允许 development/production")
    production = environment == "production"
    debug_value = env.get("SB_DEBUG", "false").lower()
    if debug_value not in {"true", "false", "1", "0"} or (production and debug_value in {"true", "1"}):
        raise ConfigurationError("SB_DEBUG 无效或在生产启用")
    secret = required(env, "SB_SECRET_KEY") if production else env.get("SB_SECRET_KEY") or secrets.token_urlsafe(64)
    if production and (len(secret) < 50 or len(set(secret)) < 5 or example_secret(secret)):
        raise ConfigurationError("SB_SECRET_KEY 必须是足够长的随机值，不得使用示例")
    origin = required(env, "SB_PUBLIC_ORIGIN") if production else env.get("SB_PUBLIC_ORIGIN", "http://localhost:5173")
    parsed_origin = parse_url(origin, "SB_PUBLIC_ORIGIN")
    if (parsed_origin.scheme not in ({"https"} if production else {"http", "https"})
            or parsed_origin.username is not None or parsed_origin.password is not None
            or parsed_origin.path or parsed_origin.query or parsed_origin.fragment):
        raise ConfigurationError("SB_PUBLIC_ORIGIN 必须是无路径和凭据的合法来源，生产必须 HTTPS")
    hosts_value = required(env, "SB_ALLOWED_HOSTS") if production else env.get("SB_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
    hosts = [host.strip().lower() for host in hosts_value.split(",")]
    if not all(valid_host(host) for host in hosts):
        raise ConfigurationError("SB_ALLOWED_HOSTS 必须列出精确主机名")
    origin_host = f"[{parsed_origin.hostname}]" if ":" in parsed_origin.hostname else parsed_origin.hostname
    if origin_host.lower() not in hosts:
        raise ConfigurationError("SB_ALLOWED_HOSTS 必须包含 SB_PUBLIC_ORIGIN 的主机")
    if env.get("SB_CSRF_TRUSTED_ORIGINS", origin) != origin:
        raise ConfigurationError("SB_CSRF_TRUSTED_ORIGINS 必须与 SB_PUBLIC_ORIGIN 完全一致")
    database = database_settings(required(env, "SB_DATABASE_URL"), "SB_DATABASE_URL", production)
    if env.get("SB_MIGRATION_DATABASE_URL"):
        migration = database_settings(env["SB_MIGRATION_DATABASE_URL"], "SB_MIGRATION_DATABASE_URL", production)
        if database["USER"] == migration["USER"] or any(database[key] != migration[key] for key in ("HOST", "PORT", "NAME")):
            raise ConfigurationError("SB_MIGRATION_DATABASE_URL 必须使用同库的独立迁移角色")
    mode = env.get("SB_MODEL_MODE", "disabled")
    if mode not in {"disabled", "demo", "local", "provider"} or (production and mode == "demo"):
        raise ConfigurationError("SB_MODEL_MODE 无效；生产禁止 demo")
    model = {"SB_MODEL_MODE": mode}
    if mode in {"local", "provider"}:
        model["SB_MODEL_NAME"] = required(env, "SB_MODEL_NAME")
        model["SB_MODEL_BASE_URL"] = required(env, "SB_MODEL_BASE_URL")
        endpoint = parse_url(model["SB_MODEL_BASE_URL"], "SB_MODEL_BASE_URL")
        if endpoint.username is not None or endpoint.password is not None or endpoint.query or endpoint.fragment:
            raise ConfigurationError("SB_MODEL_BASE_URL 不得包含凭据、查询或片段")
        if mode == "local":
            if endpoint.scheme not in {"http", "https"} or endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ConfigurationError("SB_MODEL_BASE_URL 本地模式仅允许回环地址")
        else:
            if endpoint.scheme != "https":
                raise ConfigurationError("SB_MODEL_BASE_URL 供应商模式必须 HTTPS")
            model["SB_MODEL_PROVIDER"] = required(env, "SB_MODEL_PROVIDER")
            model["SB_MODEL_API_KEY"] = required(env, "SB_MODEL_API_KEY")
            if example_secret(model["SB_MODEL_API_KEY"]):
                raise ConfigurationError("SB_MODEL_API_KEY 不得使用示例值")
    root = Path(__file__).resolve().parents[3]
    return {
        "BASE_DIR": root / "server", "SB_ENV": environment, "SECRET_KEY": secret,
        "DEBUG": debug_value in {"true", "1"}, "ALLOWED_HOSTS": hosts,
        "SB_PUBLIC_ORIGIN": origin, "CSRF_TRUSTED_ORIGINS": [origin],
        "DATABASES": {"default": database},
        "SB_RUNTIME_DB_ROLE": database["USER"],
        "SB_PRIVATE_DATA_ROOT": private_path(env, "SB_PRIVATE_DATA_ROOT", production, root / ".runtime/product-private"),
        "SB_DELETION_LEDGER_ROOT": private_path(env, "SB_DELETION_LEDGER_ROOT", False, root / ".runtime/deletion-ledger"),
        "SB_LIBRARY_ROOT": private_path(env, "SB_LIBRARY_ROOT", production, root / ".runtime/product-library"),
        "ROOT_URLCONF": "config.urls", "ASGI_APPLICATION": "config.asgi.application",
        "INSTALLED_APPS": ["django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "rest_framework", "accounts", "knowledge", "problems", "runs", "answers", "operations", "personal", "learning", "administration", "publishing"],
        "AUTH_USER_MODEL": "accounts.User",
        "AUTHENTICATION_BACKENDS": ["accounts.backends.AccountBackend", "administration.backends.AdminBackend"],
        "MIDDLEWARE": ["accounts.http.PrivateAPIMiddleware", "django.middleware.security.SecurityMiddleware", "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware"],
        "CSRF_FAILURE_VIEW": "accounts.http.csrf_failure",
        "DATA_UPLOAD_MAX_MEMORY_SIZE": 256 * 1024,
        "ACCOUNT_POLICY_VERSIONS": {"terms": "local-test-2026-09-08-recovery", "privacy": "local-test-2026-09-08-recovery"},
        "ACCOUNT_LOGIN_EMAIL_LIMIT": 10, "ACCOUNT_LOGIN_SOURCE_LIMIT": 40,
        "ACCOUNT_AUTH_WINDOW_SECONDS": 900,
        "AUTH_PASSWORD_VALIDATORS": [
            {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator", "OPTIONS": {"user_attributes": ["email", "display_name"]}},
            {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
            {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
            {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
        ],
        "REST_FRAMEWORK": {
            "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
            "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
            "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
            "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
            "UNAUTHENTICATED_USER": None,
        },
        "SESSION_COOKIE_SECURE": production, "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax", "CSRF_COOKIE_SECURE": production,
        "CSRF_COOKIE_SAMESITE": "Lax", "SESSION_COOKIE_DOMAIN": None, "CSRF_COOKIE_DOMAIN": None,
        "SECURE_SSL_REDIRECT": production, "SECURE_HSTS_SECONDS": 31536000 if production else 0,
        "SECURE_HSTS_INCLUDE_SUBDOMAINS": production, "SECURE_HSTS_PRELOAD": production,
        "SECURE_CONTENT_TYPE_NOSNIFF": True, "SECURE_REFERRER_POLICY": "same-origin",
        "X_FRAME_OPTIONS": "DENY", "APPEND_SLASH": False,
        "USE_TZ": True, "TIME_ZONE": "UTC", "LANGUAGE_CODE": "zh-hans",
        "DEFAULT_AUTO_FIELD": "django.db.models.BigAutoField",
        **model, **mail_settings(env, production),
    }
