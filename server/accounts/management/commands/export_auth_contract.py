"""旧命令兼容入口：导出或只读检查完整产品OpenAPI，不连接数据库。"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from config.contracts import contract_text


class Command(BaseCommand):
    """默认导出 server/openapi.json，--check 只检查不修复。"""
    help = "导出实际产品OpenAPI；兼容旧命令名，推荐export_api_contract"
    requires_system_checks = []

    def add_arguments(self, parser):
        """parser 为 Django 参数解析器；输出只由显式路径或项目默认值决定。"""
        parser.add_argument("--output", default=str(settings.BASE_DIR / "openapi.json"))
        parser.add_argument("--check", action="store_true")

    def handle(self, *args, **options):
        """args/options 为 CLI 参数；只生成公开静态契约，不读取任何账号记录。"""
        target = Path(options["output"])
        expected = contract_text()
        if options["check"]:
            if not target.is_file() or target.read_text(encoding="utf-8") != expected:
                raise CommandError("产品契约缺失或存在漂移，请重新导出后审查差异")
            self.stdout.write("产品契约与当前实现一致")
        else:
            target.write_text(expected, encoding="utf-8")
            self.stdout.write("产品契约已导出")
