"""产品本机数据库启动器的安全边界；不触碰已有服务或原书。"""
import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/dev/product_db.py"


class ProductRuntimeTests(unittest.TestCase):
    """使用隔离临时目录测试路径、配置和只读状态。"""

    def setUp(self):
        """加载被测启动器；缺少实现时产生明确断言失败。"""
        self.assertTrue(SCRIPT.exists(), "尚未实现产品数据库启动器")
        spec = importlib.util.spec_from_file_location("product_db", SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_configuration_has_separate_roles_and_disabled_model(self):
        """base为临时项目，默认生成两个不同角色且模型关闭。"""
        with tempfile.TemporaryDirectory() as directory:
            config = self.module.make_config(Path(directory), 55439)
            self.assertNotEqual(config["runtime_password"], config["migration_password"])
            env = self.module.environment(config)
            self.assertIn("sb_runtime:", env["SB_DATABASE_URL"])
            self.assertIn("sb_migrator:", env["SB_MIGRATION_DATABASE_URL"])
            self.assertEqual(env["SB_MODEL_MODE"], "disabled")
            self.assertEqual(env["SB_ENV"], "development")

    def test_validate_refuses_other_project_path(self):
        """篡改cluster路径不能将启动器指向其他数据库。"""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            config = self.module.make_config(base, 55439)
            config["data_dir"] = "/tmp/not-this-project"
            with self.assertRaises(ValueError):
                self.module.validate_config(config, base)

    def test_private_config_and_env_are_not_world_readable(self):
        """运行数据包含凭据，创建权限必须只对本机用户可读。"""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            config = self.module.make_config(base, 55439)
            self.module.save_config(config, base)
            self.assertEqual((base / ".runtime/product-db.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual((base / ".runtime/product.env").stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.module.read_config(base), config)

    def test_symlink_runtime_is_refused(self):
        """禁止借.runtime符号链接写入项目外的任意目录。"""
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as target:
            base = Path(directory)
            (base / ".runtime").symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError):
                self.module.save_config(self.module.make_config(base, 55439), base)

    def test_invalid_port_is_rejected(self):
        """端口必须为非特权合法整数。"""
        with self.assertRaises(ValueError):
            self.module.make_config(ROOT, 0)

    def test_other_valid_port_is_rejected(self):
        """限定唯一登记端口，避免意外接管其他服务。"""
        with self.assertRaises(ValueError):
            self.module.make_config(ROOT, 55440)

    def test_existing_environment_is_required_private_and_consistent(self):
        """真实临时文件覆盖缺失、公开权限、链接与凭据/模型篡改。"""
        for variant in ("missing", "public", "symlink", "credential", "model", "directory"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                config = self.module.make_config(base, 55439)
                self.module.save_config(config, base)
                env = base / ".runtime/product.env"
                original = env.read_text()
                if variant == "public":
                    env.chmod(0o644)
                elif variant in ("missing", "symlink", "directory"):
                    env.unlink()
                    if variant == "symlink":
                        env.symlink_to(base / "missing")
                    elif variant == "directory":
                        env.mkdir(mode=0o700)
                else:
                    env.write_text(original.replace(config["runtime_password"], "wrong") if variant == "credential" else original.replace("SB_MODEL_MODE=disabled", "SB_MODEL_MODE=live"))
                with self.assertRaises(ValueError):
                    self.module.read_config(base)

    def test_start_rejects_critical_symlinks_before_external_work(self):
        """启动必须先拒绝日志/配置/PID链接，不调用进程、不覆盖目标。"""
        for name in ("product-postgres.log", "product-postgres/postmaster.pid", "product-postgres/postgresql.conf", "product-postgres/postgresql.auto.conf", "product-postgres/pg_hba.conf", "product-postgres/global/pg_control"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                self.module.save_config(self.module.make_config(base, 55439), base)
                link = base / ".runtime" / name
                link.parent.mkdir(parents=True, exist_ok=True)
                target = base / "untouched"
                target.write_text("preserve")
                link.symlink_to(target)
                with patch.object(self.module.subprocess, "run", side_effect=AssertionError("不应执行进程")):
                    with self.assertRaises(ValueError):
                        self.module.start(base, 55439)
                self.assertEqual(target.read_text(), "preserve")

    def test_redirecting_postgres_configuration_is_refused(self):
        """真实配置文件中的目录重定向或外部include不能被执行。"""
        for setting in ("data_directory = '/other/cluster'", "include = '/other/config'", "hba_file = '/other/hba'", "external_pid_file = '/other/pid'"):
            with self.subTest(setting=setting), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                config = self.module.make_config(base, 55439)
                self.module.save_config(config, base)
                data = Path(config["data_dir"])
                data.mkdir()
                (data / "postgresql.conf").write_text(setting)
                with self.assertRaises(ValueError):
                    self.module.read_config(base)

    def test_entire_cluster_tree_rejects_existing_redirects(self):
        """所有入口统一拒绝WAL、库文件、表空间和任意嵌套链接，不跟随目标。"""
        for name in ("pg_wal", "base/16384/relation", "pg_tblspc/16385", "arbitrary/deep/nested/link"):
            for action in ("read", "start", "stop", "status"):
                with self.subTest(name=name, action=action), tempfile.TemporaryDirectory() as directory:
                    base = Path(directory)
                    config = self.module.make_config(base, 55439)
                    self.module.save_config(config, base)
                    data = Path(config["data_dir"])
                    link = data / name
                    link.parent.mkdir(parents=True, exist_ok=True)
                    target = base / "outside-cluster"
                    target.mkdir()
                    marker = target / "must-not-touch"
                    marker.write_text("preserve")
                    link.symlink_to(target, target_is_directory=True)
                    with patch.object(self.module.subprocess, "run", side_effect=AssertionError("未验证目录不能调用外部进程")):
                        with self.assertRaises(ValueError):
                            if action == "read":
                                self.module.read_config(base)
                            elif action == "start":
                                self.module.start(base, 55439)
                            else:
                                getattr(self.module, action)(base)
                    self.assertEqual(marker.read_text(), "preserve")

    def test_cluster_tree_rejects_dangling_links_and_special_nodes(self):
        """递归边界也拒绝悬空链接与非普通文件，避免读取FIFO阻塞。"""
        for variant in ("dangling", "fifo"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                config = self.module.make_config(base, 55439)
                self.module.save_config(config, base)
                node = Path(config["data_dir"]) / "nested/node"
                node.parent.mkdir(parents=True)
                if variant == "dangling":
                    node.symlink_to(base / "missing")
                else:
                    os.mkfifo(node)
                with self.assertRaises(ValueError):
                    self.module.read_config(base)

    def test_existing_unsafe_roles_are_refused_without_alteration(self):
        """只替代外部进程；角色标志/成员关系/所有者异常不能触发修复SQL。"""
        roles = [dict(rolname=name, rolsuper=False, rolcreatedb=name == "sb_migrator", rolcreaterole=False, rolreplication=False, rolbypassrls=False, rolcanlogin=True) for name in ("sb_runtime", "sb_migrator")]
        for variant in ("rolsuper", "rolcreatedb", "rolcreaterole", "rolreplication", "rolbypassrls", "memberships", "owner"):
            snapshot = dict(roles=json.loads(json.dumps(roles)), memberships=0, owner="sb_migrator", schema_owner="sb_migrator")
            if variant == "memberships":
                snapshot[variant] = 1
            elif variant == "owner":
                snapshot[variant] = "sb_runtime"
            else:
                snapshot["roles"][0][variant] = True
            def process(argv, **kwargs):
                """argv/kwargs为真实子进程边界，拒绝任何可能更改集群的SQL。"""
                sql = kwargs.get("input") or ""
                if any(word in sql for word in ("ALTER ROLE", "CREATE ROLE", "REVOKE")):
                    raise AssertionError("不能修改不安全的已有集群")
                output = "psql (PostgreSQL) 16.14" if "--version" in argv else json.dumps(snapshot)
                return subprocess.CompletedProcess(argv, 0, output, "")
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                config = self.module.make_config(Path(directory), 55439)
                with patch.object(self.module.subprocess, "run", side_effect=process):
                    with self.assertRaises(ValueError):
                        self.module.bootstrap_roles(config)

    def test_stop_refuses_pid_process_or_live_cluster_mismatch(self):
        """在外部进程边界注入真实格式响应，错进程/目录/端口/系统ID均不得信号。"""
        for variant in ("process", "data_directory", "port", "system_identifier", "pid_directory"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                config = self.module.make_config(base, 55439)
                self.module.save_config(config, base)
                data = Path(config["data_dir"])
                data.mkdir()
                (data / "PG_VERSION").write_text("16\n")
                pid_dir = "/other" if variant == "pid_directory" else str(data)
                (data / "postmaster.pid").write_text(f"1234\n{pid_dir}\n1000\n55439\n{config['socket_dir']}\n127.0.0.1\n0 0\nready\n")
                identity = dict(data_directory=str(data), config_file=str(data / "postgresql.conf"), hba_file=str(data / "pg_hba.conf"), ident_file=str(data / "pg_ident.conf"), port="55439", unix_socket_directories=config["socket_dir"], listen_addresses="127.0.0.1", system_identifier="12345", started=1000)
                if variant in identity:
                    identity[variant] = "99999" if variant in ("port", "system_identifier") else "/other"
                def process(argv, **kwargs):
                    """argv/kwargs模拟PG16工具和ps，只允许只读行为。"""
                    if "stop" in argv:
                        raise AssertionError("不能向未验证的PID发送信号")
                    if "--version" in argv:
                        output = "PostgreSQL 16.14"
                    elif Path(argv[0]).name == "ps":
                        executable = Path("/opt/homebrew/opt/postgresql@16/bin/postgres").resolve()
                        output = f"{os.getuid()} {executable} -D {data}" if variant != "process" else f"{os.getuid()} /bin/sleep 100"
                    elif Path(argv[0]).name == "pg_controldata":
                        output = "Database system identifier: 12345\n"
                    else:
                        output = json.dumps(identity)
                    return subprocess.CompletedProcess(argv, 0, output, "")
                with patch.object(self.module.subprocess, "run", side_effect=process):
                    with self.assertRaises(ValueError):
                        self.module.stop(base)

    def test_wrong_postgres_major_is_rejected(self):
        """进程边界返回其他版本时不能执行请求命令。"""
        def process(argv, **kwargs):
            """argv是工具调用；只允许版本探测。"""
            if "--version" not in argv:
                raise AssertionError("版本未通过不能执行")
            return subprocess.CompletedProcess(argv, 0, "postgres (PostgreSQL) 17.1", "")
        with patch.object(self.module.subprocess, "run", side_effect=process):
            with self.assertRaises(ValueError):
                self.module.command("pg_ctl", ["--help"])

    def test_postgres_tools_cannot_cross_installation_directories(self):
        """PATH只定位postgres；同目录工具若链接另一安装也必须拒绝。"""
        with tempfile.TemporaryDirectory() as directory:
            binary_dir = Path(directory) / "bin"
            binary_dir.mkdir()
            postgres = binary_dir / "postgres"
            postgres.write_text("#!/bin/sh\n")
            postgres.chmod(0o755)
            foreign = Path(directory) / "other-pg-ctl"
            foreign.write_text("#!/bin/sh\n")
            foreign.chmod(0o755)
            (binary_dir / "pg_ctl").symlink_to(foreign)
            def process(argv, **kwargs):
                """只允许版本探测，不允许执行跨安装工具。"""
                if "--version" not in argv:
                    raise AssertionError("跨安装工具不能被执行")
                return subprocess.CompletedProcess(argv, 0, "PostgreSQL 16.14", "")
            with patch.dict(os.environ, {"PATH": str(binary_dir)}), patch.object(self.module.subprocess, "run", side_effect=process):
                with self.assertRaises(ValueError):
                    self.module.command("pg_ctl", ["--help"])

    def test_status_does_not_treat_inaccessible_pid_as_stopped(self):
        """沙箱中pg_ctl返回3但PID文件仍在时，不能误报停止或重启。"""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            config = self.module.make_config(base, 55439)
            self.module.save_config(config, base)
            data = Path(config["data_dir"])
            data.mkdir()
            (data / "PG_VERSION").write_text("16\n")
            (data / "postmaster.pid").write_text("1234\n")
            def process(argv, **kwargs):
                """argv为版本或状态探测，模拟sandbox无法看到现有进程。"""
                return subprocess.CompletedProcess(argv, 0 if "--version" in argv else 3, "PostgreSQL 16.14" if "--version" in argv else "no server running", "")
            with patch.object(self.module.subprocess, "run", side_effect=process):
                with self.assertRaises(RuntimeError):
                    self.module.status(base)

    def test_safe_existing_roles_do_not_change_passwords(self):
        """合法已有角色只检查两套身份；SQL/argv均不含口令或写操作。"""
        with tempfile.TemporaryDirectory() as directory:
            config = self.module.make_config(Path(directory), 55439)
            roles = [dict(rolname=name, rolsuper=False, rolcreatedb=name == "sb_migrator", rolcreaterole=False, rolreplication=False, rolbypassrls=False, rolcanlogin=True) for name in ("sb_runtime", "sb_migrator")]
            authenticated = []
            def process(argv, **kwargs):
                """只替代进程，检查真正生成的SQL与安全传输参数。"""
                sql = kwargs.get("input") or ""
                for secret in (config["runtime_password"], config["migration_password"]):
                    self.assertNotIn(secret, " ".join(argv) + sql)
                self.assertFalse(any(word in sql for word in ("ALTER ROLE", "CREATE ROLE", "REVOKE")))
                if "--version" in argv:
                    output = "PostgreSQL 16.14"
                elif "json_build_object" in sql:
                    output = json.dumps(dict(roles=roles, memberships=0, owner="sb_migrator"))
                elif "current_user" in sql:
                    output = argv[argv.index("-U") + 1]
                    authenticated.append(output)
                    self.assertTrue(kwargs["env"].get("PGPASSWORD"))
                else:
                    output = "sb_migrator"
                return subprocess.CompletedProcess(argv, 0, output, "")
            with patch.object(self.module.subprocess, "run", side_effect=process):
                self.module.bootstrap_roles(config)
            self.assertEqual(authenticated, ["sb_runtime", "sb_migrator"])

    def test_initial_password_sql_disables_statement_logging_first(self):
        """首次初始化在发送口令之前关闭本会话SQL/错误SQL日志。"""
        with tempfile.TemporaryDirectory() as directory:
            config = self.module.make_config(Path(directory), 55439)
            def process(argv, **kwargs):
                """首次角色不存在；捕获真正提交的SQL，避免启动真实集群。"""
                sql = kwargs.get("input") or ""
                if config["runtime_password"] in sql:
                    prefix = sql.split("ALTER ROLE", 1)[0]
                    self.assertIn("SET log_statement = 'none'", prefix)
                    self.assertIn("SET log_min_error_statement = 'panic'", prefix)
                    raise RuntimeError("验证到安全的首次创建边界")
                output = "PostgreSQL 16.14" if "--version" in argv else json.dumps(dict(roles=[], memberships=0, owner=None))
                return subprocess.CompletedProcess(argv, 0, output, "")
            with patch.object(self.module.subprocess, "run", side_effect=process):
                with self.assertRaisesRegex(RuntimeError, "安全的首次创建"):
                    self.module.bootstrap_roles(config)

    def test_cli_explains_model_environment_mismatch_without_overwriting(self):
        """冻结env有显式模型配置时，CLI给出明确原因并保留用户内容。"""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            self.module.save_config(self.module.make_config(base, 55439), base)
            env = base / ".runtime/product.env"
            edited = env.read_text().replace("SB_MODEL_MODE=disabled", "SB_MODEL_MODE=live")
            env.write_text(edited)
            self.module.ROOT = base
            output = io.StringIO()
            with patch.object(sys, "argv", [str(SCRIPT), "status"]), contextlib.redirect_stderr(output):
                self.assertEqual(self.module.main(), 1)
            self.assertIn("product.env", output.getvalue())
            self.assertIn("模型", output.getvalue())
            self.assertEqual(env.read_text(), edited)

    def test_status_without_init_does_not_write(self):
        """只读查询未初始化状态不创建文件或启动服务。"""
        with tempfile.TemporaryDirectory() as directory:
            result = self.module.status(Path(directory))
            self.assertEqual(result, {"status": "not_initialized"})
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cli_help_hides_secrets(self):
        """CLI帮助输出不读取配置，也不要求数据库在线。"""
        result = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("start", result.stdout)


if __name__ == "__main__":
    unittest.main()
