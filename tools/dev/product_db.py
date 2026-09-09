"""只管理本项目开发PostgreSQL；不安装软件、不修改系统服务、不打印凭据。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


class EnvironmentMismatch(ValueError):
    """冻结开发环境被人工修改时明确报错，保留修改和凭据。"""


def make_config(base: Path, port: int) -> dict:
    """base为项目根目录，port为独立非特权端口；只生成内存配置。"""
    if not isinstance(port, int) or isinstance(port, bool) or port != 55439:
        raise ValueError("本项目开发数据库只支持端口55439")
    base = base.resolve()
    suffix = hashlib.sha256(str(base).encode()).hexdigest()[:16]
    return {
        "schema_version": 1, "project": str(base), "port": port,
        "data_dir": str(base / ".runtime/product-postgres"),
        "socket_dir": f"/private/tmp/sb-product-pg-{suffix}",
        "runtime_password": secrets.token_urlsafe(32),
        "migration_password": secrets.token_urlsafe(32),
        "secret_key": secrets.token_urlsafe(64),
    }


def validate_config(config: dict, base: Path) -> None:
    """校验config仅指向base拥有的开发目录，拒绝路径篡改与符号链接。"""
    base = base.resolve()
    expected = make_config(base, config.get("port"))
    for key in ("schema_version", "project", "data_dir", "socket_dir"):
        if config.get(key) != expected[key]:
            raise ValueError("开发数据库配置不属于当前项目")
    for key in ("runtime_password", "migration_password", "secret_key"):
        if not isinstance(config.get(key), str) or not re.fullmatch(r"[A-Za-z0-9_-]{40,100}", config[key]):
            raise ValueError("开发凭据格式不合法")
    if config["runtime_password"] == config["migration_password"]:
        raise ValueError("运行和迁移凭据必须分离")
    for path in (base / ".runtime", Path(config["data_dir"]), Path(config["socket_dir"])):
        if path.is_symlink() or (path.exists() and (not path.is_dir() or path.stat().st_uid != os.getuid())):
            raise ValueError("开发路径必须是本用户拥有的真实目录")
    validate_cluster_files(config)


def owned_file(path: Path, private: bool = False, required: bool = False) -> None:
    """path须为当前用户普通文件；private要求0600，required要求存在。"""
    if not path.exists() and not path.is_symlink():
        if required:
            raise ValueError("缺少已登记的运行文件")
        return
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or (private and stat.S_IMODE(info.st_mode) != 0o600):
        raise ValueError("运行文件必须为当前用户拥有的安全普通文件")


def validate_cluster_files(config: dict) -> None:
    """config必须对应完整自管集群；统一拒绝整棵数据树的链接、异主节点与外部配置。"""
    data = Path(config["data_dir"])
    pending = [data] if data.exists() or data.is_symlink() else []
    while pending:
        path = pending.pop()
        info = path.lstat()
        if info.st_uid != os.getuid() or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ValueError("自管集群整棵目录树只能包含本用户拥有的普通文件和目录；拒绝链接或外部表空间")
        if stat.S_ISDIR(info.st_mode):
            with os.scandir(path) as entries:
                pending.extend(Path(entry.path) for entry in entries)
    for name in ("PG_VERSION", "postgresql.conf", "postgresql.auto.conf", "pg_hba.conf", "pg_ident.conf", "postmaster.pid", "postmaster.opts", "global/pg_control"):
        owned_file(data / name)
    owned_file(Path(config["project"]) / ".runtime/product-postgres.log")
    if (data / "PG_VERSION").exists() and (data / "PG_VERSION").read_text().strip() != "16":
        raise ValueError("仅支持PostgreSQL16集群")
    for name in ("postgresql.conf", "postgresql.auto.conf"):
        path = data / name
        if path.exists() and re.search(r"^\s*(?:include(?:_dir|_if_exists)?|data_directory|config_file|hba_file|ident_file|external_pid_file)\b", path.read_text(), re.M | re.I):
            raise ValueError("拒绝集群配置重定向；请人工核对登记目录")


def environment(config: dict) -> dict:
    """从已校验config生成仅本机使用的环境，不向终端输出值。
    模型与知识根允许部署者经config显式登记（如provider模式）；未登记时保持原默认。"""
    base = Path(config["project"])
    validate_config(config, base)
    endpoint = f"127.0.0.1:{config['port']}/sb_product"
    environment_dict = {
        "SB_ENV": "development", "SB_SECRET_KEY": config["secret_key"],
        "SB_PUBLIC_ORIGIN": "http://127.0.0.1:5173", "SB_ALLOWED_HOSTS": "127.0.0.1,localhost,testserver",
        "SB_DATABASE_URL": f"postgresql://sb_runtime:{config['runtime_password']}@{endpoint}",
        "SB_MIGRATION_DATABASE_URL": f"postgresql://sb_migrator:{config['migration_password']}@{endpoint}",
        "SB_PRIVATE_DATA_ROOT": str(base / ".runtime/private"),
        "SB_LIBRARY_ROOT": config.get("sb_library_root") or str(base / "examples"),
        "SB_MODEL_MODE": config.get("sb_model_mode", "disabled"),
    }
    if environment_dict["SB_MODEL_MODE"] == "provider":
        environment_dict.update({
            "SB_MODEL_NAME": config.get("sb_model_name", ""),
            "SB_MODEL_BASE_URL": config.get("sb_model_base_url", ""),
            "SB_MODEL_PROVIDER": config.get("sb_model_provider", "openai-compatible"),
            "SB_MODEL_API_KEY": config.get("sb_model_api_key", ""),
        })
    for optional in ("SB_CALL_POLICY", "SB_MODEL_EXTRA_JSON"):
        value = config.get(optional.lower())
        if value:
            environment_dict[optional] = value
    return environment_dict


def private_write(path: Path, content: str) -> None:
    """以独占0600文件写入本次新生成的运行数据，拒绝覆盖已有配置。"""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)


def save_config(config: dict, base: Path) -> None:
    """将config保存到base私有运行目录；已有配置不覆盖。"""
    validate_config(config, base)
    runtime = base.resolve() / ".runtime"
    runtime.mkdir(mode=0o700, exist_ok=True)
    if runtime.stat().st_mode & 0o077:
        raise ValueError(".runtime目录必须仅本用户可读写（0700）")
    private_write(runtime / "product.env", "".join(f"{key}={value}\n" for key, value in environment(config).items()))
    private_write(runtime / "product-db.json", json.dumps(config, ensure_ascii=False, indent=2) + "\n")


def read_config(base: Path) -> dict | None:
    """读取base所属配置，未初始化返回None；不接受符号链接或公开凭据。"""
    if (base / ".runtime").is_symlink():
        raise ValueError(".runtime不能是符号链接")
    path = base / ".runtime/product-db.json"
    if not path.exists() and not path.is_symlink():
        return None
    owned_file(path, private=True, required=True)
    config = json.loads(path.read_text(encoding="utf-8"))
    validate_config(config, base)
    env_path = base / ".runtime/product.env"
    owned_file(env_path, private=True, required=True)
    expected = "".join(f"{key}={value}\n" for key, value in environment(config).items())
    if env_path.read_text(encoding="utf-8") != expected:
        raise EnvironmentMismatch("product.env与固定生成配置不一致（包括模型设置）；请人工核对，不自动覆盖")
    return config


def tool_path(name: str) -> Path:
    """name为PG工具名；从postgres解析单一安装目录并验证16主版本。"""
    installed = shutil.which("postgres")
    if not installed or name not in {"postgres", "pg_ctl", "initdb", "psql", "pg_controldata"}:
        raise RuntimeError("缺少受支持的PostgreSQL16工具；不自动安装")
    binary_dir = Path(installed).resolve().parent
    executable = (binary_dir / name).resolve()
    if executable.parent != binary_dir:
        raise ValueError("工具不能跨越PostgreSQL安装目录")
    result = subprocess.run([str(executable), "--version"], capture_output=True, text=True, timeout=10)
    if result.returncode or not re.search(r"\b16\.\d+\b", result.stdout):
        raise ValueError("工具必须来自同一PostgreSQL16安装目录")
    return executable


def command(name: str, arguments: list[str], input_text: str | None = None, check: bool = True, password: str | None = None) -> subprocess.CompletedProcess:
    """执行已安装的PostgreSQL工具name；arguments是参数，敏感SQL只经stdin发送。"""
    executable = tool_path(name)
    process_env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    process_env.update(LC_ALL="C", PGCONNECT_TIMEOUT="5")
    if password is not None:
        process_env["PGPASSWORD"] = password
    result = subprocess.run([str(executable), *arguments], input=input_text, capture_output=True, text=True, timeout=45, env=process_env)
    if check and result.returncode:
        raise RuntimeError(f"{name}执行失败，退出码{result.returncode}；未输出可能含敏感信息的原始报文")
    return result


def query(config: dict, sql: str, database: str = "postgres") -> str:
    """config为已登记实例；在database只经stdin执行sql并返回私有结果。"""
    return command("psql", ["-X", "-w", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-h", config["socket_dir"], "-p", str(config["port"]), "-U", "sb_bootstrap", "-d", database], sql).stdout.strip()


def verify_identity(config: dict) -> None:
    """独立核对config的PID、当前进程、SQL路径端口和磁盘系统标识，失败不发信号。"""
    validate_config(config, Path(config["project"]))
    data = Path(config["data_dir"])
    pid_path = data / "postmaster.pid"
    owned_file(pid_path, required=True)
    original = pid_path.read_text()
    lines = original.splitlines()
    if len(lines) < 8 or not lines[0].isdigit() or int(lines[0]) <= 1 or lines[1] != str(data) or lines[3] != str(config["port"]) or lines[4] != config["socket_dir"] or lines[5] != "127.0.0.1" or lines[7].strip() != "ready":
        raise ValueError("PID文件与本项目实例不一致")
    process = subprocess.run(["/bin/ps", "-ww", "-p", lines[0], "-o", "uid=", "-o", "command="], capture_output=True, text=True, timeout=10)
    fields = process.stdout.strip().split(maxsplit=1)
    executable = str(tool_path("postgres"))
    if process.returncode or len(fields) != 2 or fields[0] != str(os.getuid()) or not fields[1].startswith(executable + " ") or not re.search(r"(?:^|\s)-D " + re.escape(str(data)) + r"(?:\s|$)", fields[1]):
        raise ValueError("PID不属于本项目PostgreSQL进程")
    identity = json.loads(query(config, """
SELECT json_build_object('data_directory',current_setting('data_directory'),
 'config_file',current_setting('config_file'),'hba_file',current_setting('hba_file'),
 'ident_file',current_setting('ident_file'),'port',current_setting('port'),
 'unix_socket_directories',current_setting('unix_socket_directories'),
 'listen_addresses',current_setting('listen_addresses'),
 'system_identifier',(SELECT system_identifier::text FROM pg_control_system()),
 'started',extract(epoch FROM pg_postmaster_start_time()));
"""))
    expected = dict(data_directory=str(data), config_file=str(data / "postgresql.conf"), hba_file=str(data / "pg_hba.conf"), ident_file=str(data / "pg_ident.conf"), port=str(config["port"]), unix_socket_directories=config["socket_dir"], listen_addresses="127.0.0.1")
    control = command("pg_controldata", [str(data)]).stdout
    identifier = re.search(r"^Database system identifier:\s*(\d+)\s*$", control, re.M)
    if any(identity.get(key) != value for key, value in expected.items()) or not identifier or identity.get("system_identifier") != identifier[1] or abs(float(identity.get("started", 0)) - int(lines[2])) >= 2:
        raise ValueError("在线集群身份、端口或配置与登记数据不一致")
    owned_file(pid_path, required=True)
    if pid_path.read_text() != original:
        raise ValueError("验证期间PID发生变化，拒绝操作")


def status(base: Path) -> dict:
    """只读检查base的专用实例，不创建目录、不枚举其他数据库。"""
    config = read_config(base)
    if config is None:
        return {"status": "not_initialized"}
    if not (Path(config["data_dir"]) / "PG_VERSION").exists():
        return {"status": "configured_not_initialized", "port": config["port"]}
    result = command("pg_ctl", ["-D", config["data_dir"], "status"], check=False)
    if result.returncode == 0:
        verify_identity(config)
    elif result.returncode != 3 or (Path(config["data_dir"]) / "postmaster.pid").exists():
        raise RuntimeError("无法确定登记实例状态（PID仍在或进程不可访问）；拒绝重复启动")
    return {"status": "running" if result.returncode == 0 else "stopped", "port": config["port"]}


def bootstrap_roles(config: dict) -> None:
    """在本项目实例内建立分离角色和数据库；config凭据不进入进程参数。"""
    if validate_roles(config):
        return
    options = ["-X", "-w", "-v", "ON_ERROR_STOP=1", "-h", config["socket_dir"], "-p", str(config["port"]), "-U", "sb_bootstrap"]
    sql = """
SET log_statement = 'none';
SET log_min_error_statement = 'panic';
SET log_min_duration_statement = -1;
SET log_min_duration_sample = -1;
SET log_transaction_sample_rate = 0;
DO $body$
BEGIN
 IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='sb_migrator') THEN CREATE ROLE sb_migrator LOGIN CREATEDB; END IF;
 IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='sb_runtime') THEN CREATE ROLE sb_runtime LOGIN; END IF;
END $body$;
"""
    sql += f"ALTER ROLE sb_migrator PASSWORD '{config['migration_password']}';\n"
    sql += f"ALTER ROLE sb_runtime PASSWORD '{config['runtime_password']}';\n"
    sql += "SELECT 'CREATE DATABASE sb_product OWNER sb_migrator' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='sb_product')\\gexec\n"
    command("psql", [*options, "-d", "postgres"], sql)
    command("psql", [*options, "-d", "sb_product"], """
REVOKE ALL ON DATABASE sb_product FROM PUBLIC;
GRANT CONNECT ON DATABASE sb_product TO sb_runtime;
ALTER SCHEMA public OWNER TO sb_migrator;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO sb_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE sb_migrator IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO sb_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE sb_migrator IN SCHEMA public GRANT USAGE,SELECT ON SEQUENCES TO sb_runtime;
""")
    if not validate_roles(config):
        raise ValueError("角色初始化未通过校验")


def validate_roles(config: dict) -> bool:
    """只读核对config实例角色、成员关系、库归属与两套口令；完全未初始化返回False。"""
    snapshot = json.loads(query(config, """
SELECT json_build_object('roles',(SELECT coalesce(json_agg(r),'[]'::json) FROM
 (SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolcanlogin
 FROM pg_roles WHERE rolname IN ('sb_runtime','sb_migrator')) r),
 'memberships',(SELECT count(*) FROM pg_auth_members WHERE member IN
 (SELECT oid FROM pg_roles WHERE rolname IN ('sb_runtime','sb_migrator'))),
 'owner',(SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='sb_product'));
"""))
    if snapshot.get("roles") == [] and snapshot.get("owner") is None:
        return False
    roles = {role["rolname"]: role for role in snapshot.get("roles", [])}
    if set(roles) != {"sb_runtime", "sb_migrator"} or snapshot.get("memberships") != 0 or snapshot.get("owner") != "sb_migrator":
        raise ValueError("已有角色成员关系或数据库所有者不安全；不自动修复")
    for name, role in roles.items():
        expected = dict(rolsuper=False, rolcreatedb=name == "sb_migrator", rolcreaterole=False, rolreplication=False, rolbypassrls=False, rolcanlogin=True)
        if any(role.get(key) is not value for key, value in expected.items()):
            raise ValueError("已有数据库角色权限不安全；不自动修复")
    if query(config, "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='public';", "sb_product") != "sb_migrator":
        raise ValueError("public schema所有者与登记迁移角色不一致")
    for role, key in (("sb_runtime", "runtime_password"), ("sb_migrator", "migration_password")):
        result = command("psql", ["-X", "-w", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-h", "127.0.0.1", "-p", str(config["port"]), "-U", role, "-d", "sb_product"], "SELECT current_user;", password=config[key])
        if result.stdout.strip() != role:
            raise ValueError("数据库登录身份与登记凭据不一致")
    return True


def start(base: Path, port: int) -> dict:
    """初始化或启动base专属集群，始终只绑定回环；绝不重置已有数据库。"""
    config = read_config(base)
    make_config(base, port)
    if config is None:
        config = make_config(base, port)
        if Path(config["data_dir"]).exists():
            raise ValueError("发现未登记的数据目录，拒绝接管")
        save_config(config, base)
    if config["port"] != port:
        raise ValueError("已有实例端口不同，请用已登记端口，不自动改配置")
    socket_dir = Path(config["socket_dir"])
    socket_dir.mkdir(mode=0o700, exist_ok=True)
    if socket_dir.stat().st_mode & 0o077:
        raise ValueError("数据库socket目录必须为0700")
    if not (Path(config["data_dir"]) / "PG_VERSION").exists():
        command("initdb", ["-D", config["data_dir"], "-U", "sb_bootstrap", "--auth-local=trust", "--auth-host=scram-sha-256", "--encoding=UTF8", "--locale=C"])
    if status(base)["status"] != "running":
        validate_cluster_files(config)
        options = shlex.join(["-h", "127.0.0.1", "-p", str(port), "-k", str(socket_dir), "-c", f"data_directory={config['data_dir']}", "-c", f"config_file={config['data_dir']}/postgresql.conf"])
        command("pg_ctl", ["-D", config["data_dir"], "-l", str(base / ".runtime/product-postgres.log"), "-o", options, "-w", "start"])
    verify_identity(config)
    bootstrap_roles(config)
    return {"status": "running", "port": port, "environment_file": str(base / ".runtime/product.env"), "model": "disabled"}


def stop(base: Path) -> dict:
    """仅优雅停止base已登记实例；不删除目录，保留可恢复数据。"""
    config = read_config(base)
    if config and status(base)["status"] == "running":
        verify_identity(config)
        command("pg_ctl", ["-D", config["data_dir"], "-m", "fast", "-w", "stop"])
    return status(base)


def main() -> int:
    """CLI入口，输出仅脱敏状态；参数start/status/stop用于当前固定项目。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "status", "stop"))
    parser.add_argument("--port", type=int, default=55439)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        result = start(ROOT, args.port) if args.action == "start" else stop(ROOT) if args.action == "stop" else status(ROOT)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except EnvironmentMismatch:
        print("开发数据库操作失败：product.env与冻结生成配置不一致（含模型设置）。请人工核对；文件未覆盖。", file=sys.stderr)
        return 1
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"开发数据库操作失败：{type(error).__name__}。请核对本项目路径、权限、端口和已安装的PostgreSQL；没有删除数据。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
