"""独立测试库浏览器联调：真实API/队列，自编材料和固定提案，不用于生产或模型效果验收。"""
import asyncio
import json
import mimetypes
import os
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]


def main():
    """无参数；独占test_sb_product和回环8020，退出清理精确fixture并销毁测试库。"""
    sys.path[:0] = [str(ROOT / 'server'), str(ROOT)]
    os.environ['DJANGO_SETTINGS_MODULE'] = 'tests.integration_settings'
    import django
    django.setup()
    from django.core.asgi import get_asgi_application
    from django.contrib.sessions.models import Session
    from django.db import connections
    from django.test import override_settings
    from tests.database_runner import RuntimeDatabaseRunner
    from tests.knowledge_fixtures import KnowledgeFixtureCase
    from tests.answer_fixtures import AnswerProvider
    from runs.worker import process_one
    from psycopg.types.json import Jsonb
    import uvicorn

    dist = ROOT / 'web/dist'
    if not (dist / 'index.html').is_file():
        raise RuntimeError('先执行web构建')
    runner = RuntimeDatabaseRunner(verbosity=0, interactive=False)
    previous = runner.setup_databases()
    fixture, stopped, worker = KnowledgeFixtureCase(), threading.Event(), None
    try:
        fixture.setUp()
        owners = [fixture.owner_a, fixture.owner_b, fixture.owner_c]
        def clean_private():
            """无参数；仅固定测试库/本fixture owner，解除循环关联再逆序删除。"""
            fixture.manager.execute('UPDATE problems_message SET run_id=NULL WHERE owner_id=ANY(%s)', [owners])
            fixture.manager.execute('UPDATE learning_learningturn SET run_id=NULL WHERE owner_id=ANY(%s)', [owners])
            # 先删除较晚反馈再删除其回答/练习，保留真实父域RESTRICT约束。
            turns = fixture.manager.execute('SELECT id FROM learning_learningturn WHERE owner_id=ANY(%s) ORDER BY sequence DESC', [owners]).fetchall()
            for (turn_id,) in turns:
                fixture.manager.execute('DELETE FROM learning_learningturn WHERE id=%s AND owner_id=ANY(%s)', [turn_id, owners])
            for table in ('personal_feedback', 'personal_actionrecord', 'personal_bookmark',
                          'operations_usageentry', 'operations_runreservation', 'operations_quotabucket',
                          'answers_answer', 'runs_jobevent', 'runs_analysisrun', 'runs_job',
                          'learning_learningsession', 'problems_message', 'problems_idempotencyrecord', 'problems_problem'):
                fixture.manager.execute(f'DELETE FROM {table} WHERE owner_id=ANY(%s)', [owners])
            Session.objects.all().delete()
        fixture.addCleanup(clean_private)
        for user, right in ((fixture.user_a, fixture.right_a), (fixture.user_b, fixture.right_b)):
            user.set_password('Browser-Demo-Library-628!')
            user.save(update_fields=['password'])
            fixture.change('knowledge_rightsrecord', right, allowed_uses=Jsonb(['browse', 'quote', 'analyze']))
        def work():
            """无参数；仅处理测试owner，永远显式注入自编提案，绝不读取真实provider配置。"""
            try:
                while not stopped.is_set():
                    for owner in owners:
                        if stopped.is_set():
                            break
                        process_one(owner, provider=AnswerProvider())
                    stopped.wait(0.15)
            finally:
                connections.close_all()
        with override_settings(ALLOWED_HOSTS=['127.0.0.1', 'localhost'],
                SB_PUBLIC_ORIGIN='http://127.0.0.1:8020',
                CSRF_TRUSTED_ORIGINS=['http://127.0.0.1:8020']):
            api = get_asgi_application()
            async def app(scope, receive, send):
                """scope/receive/send为ASGI协议；业务请求原样走真实Django，其余仅受限dist文件。"""
                if scope['type'] != 'http' or scope['path'].startswith(('/api/', '/health/')):
                    return await api(scope, receive, send)
                path = (dist / scope['path'].lstrip('/')).resolve()
                if not path.is_relative_to(dist.resolve()) or not path.is_file():
                    path = dist / 'index.html'
                body = path.read_bytes()
                content_type = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
                if path.name == 'index.html':
                    body = body.replace(b'<body>', '<body><div style="padding:8px;text-align:center;background:#fff3c7;color:#443800;font:14px sans-serif">独立测试库 · 自编书籍与固定提案 · 不代表真实模型效果</div>'.encode())
                await send({'type': 'http.response.start', 'status': 200, 'headers': [
                    (b'content-type', content_type.encode()), (b'cache-control', b'no-store')]})
                await send({'type': 'http.response.body', 'body': body})
            worker = threading.Thread(target=work, daemon=True)
            worker.start()
            print(json.dumps({'url': 'http://127.0.0.1:8020', 'email_a': fixture.user_a.email,
                'email_b': fixture.user_b.email, 'mode': 'self_authored_test_only'}, ensure_ascii=False), flush=True)
            config = uvicorn.Config(app, host='127.0.0.1', port=8020, log_level='warning',
                access_log=False, lifespan='off', proxy_headers=False)
            asyncio.run(uvicorn.Server(config).serve())
    finally:
        stopped.set()
        if worker:
            worker.join(timeout=15)
            if worker.is_alive():
                raise RuntimeError('测试worker尚未结束，保留测试库供核对')
        fixture.doCleanups()
        runner.teardown_databases(previous)
        print('自编联调测试库已清理', flush=True)


if __name__ == '__main__':
    main()
