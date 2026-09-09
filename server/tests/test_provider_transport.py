"""自编回环HTTP响应测试真实传输；不是供应商或真实模型效果验收。"""
import importlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from django.test import SimpleTestCase
from ai.ports import GenerationRequest, ModelFailure


class ProviderTransportTests(SimpleTestCase):
    """只监听回环随机端口，检查结构、原文、重定向、取消与超时。"""

    def setUp(self):
        """无参数；不存在实现时先明确失败；测试服务器仅返回自编内容。"""
        self.assertTrue((Path(__file__).resolve().parents[1]/'ai/provider.py').exists(), '缺少模型传输')
        self.module = importlib.import_module('ai.provider')
        self.received = []
        self.payload = {'choices':[{'message':{'content':'{"ok": true}'},'finish_reason':'stop'}],
                        'model':'actual-test-model','usage':{'prompt_tokens':12,'completion_tokens':4}}
        self.status, self.delay = 200, 0
        test = self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                """无参数；读取本测试POST并按测试配置发送自编响应。"""
                test.received.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length']))), dict(self.headers)))
                if test.delay:
                    threading.Event().wait(test.delay)
                self.send_response(test.status)
                self.send_header('Content-Type','application/json')
                if test.status == 302:
                    self.send_header('Location', '/must-not-follow')
                self.end_headers()
                try:
                    self.wfile.write(json.dumps(test.payload).encode())
                except (BrokenPipeError,ConnectionResetError):
                    pass

            def log_message(self, *args):
                """args为HTTP日志参数；不记录私有请求。"""
        self.server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread = threading.Thread(target=lambda:self.server.serve_forever(poll_interval=0.02),daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.provider = self.module.provider_from_settings({
            'SB_MODEL_MODE':'local','SB_MODEL_BASE_URL':f'http://127.0.0.1:{self.server.server_port}/v1',
            'SB_MODEL_NAME':'configured-test-model'})

    def close(self):
        """无参数；只结束本测试回环服务，不影响项目开发端口。"""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)

    def request(self, *, seconds=3, cancelled=lambda:False):
        """seconds/cancelled为本调用时限与取消信号；内容为自编样例。"""
        return GenerationRequest('extract','private test instruction',{'message':'  原话\n'},
            {'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False},
            time.monotonic()+seconds,60,cancelled)

    def test_actual_post_preserves_context_and_actual_usage(self):
        """无参数；执行真实网络POST，解析供应商报告而非配置模型名猜测计量。"""
        result = self.provider.generate(self.request())
        self.assertEqual(result.content, {'ok':True})
        self.assertEqual((result.input_tokens,result.output_tokens,result.model),(12,4,'actual-test-model'))
        path,body,headers = self.received[0]
        self.assertEqual(path,'/v1/chat/completions')
        self.assertEqual(json.loads(body['messages'][1]['content'])['message'],'  原话\n')
        self.assertEqual(body['max_tokens'],60)
        self.assertNotIn('Authorization',headers)

    def test_unknown_usage_stays_unknown(self):
        """无参数；供应商未报告token时不可填0。"""
        del self.payload['usage']
        result = self.provider.generate(self.request())
        self.assertIsNone(result.input_tokens)
        self.assertIsNone(result.output_tokens)

    def test_redirect_and_private_error_are_not_followed_or_exposed(self):
        """无参数；既不重发也不回显原始供应商错误。"""
        self.status,self.payload = 302,{'private':'secret test detail'}
        with self.assertRaises(ModelFailure) as caught:
            self.provider.generate(self.request())
        self.assertEqual(str(caught.exception),'MODEL_UNAVAILABLE')
        self.assertEqual(len(self.received),1)

    def test_cancel_and_deadline_end_wait_without_retry(self):
        """无参数；延迟响应期间取消及整次截止生效，没有隐式重试。"""
        self.delay = 0.8
        for cancel in (False,True):
            with self.subTest(cancel=cancel):
                start = time.monotonic()
                with self.assertRaises(ModelFailure) as caught:
                    self.provider.generate(self.request(seconds=0.12 if not cancel else 2,
                        cancelled=lambda:cancel and time.monotonic()-start>0.12))
                self.assertEqual(caught.exception.code,'RUN_CANCELLED' if cancel else 'RUN_TIMEOUT')
                self.assertLess(time.monotonic()-start,0.6)
        self.assertEqual(len(self.received),2)

    def test_invalid_output_and_unapproved_configuration_fail_closed(self):
        """无参数；拒绝截断JSON、越界网络配置及自动demo回退。"""
        self.payload['choices'][0]['finish_reason'] = 'length'
        with self.assertRaises(ModelFailure) as caught:
            self.provider.generate(self.request())
        self.assertEqual(caught.exception.code,'MODEL_OUTPUT_INVALID')
        self.assertEqual((caught.exception.usage.input_tokens, caught.exception.usage.output_tokens), (12, 4))
        self.assertEqual(caught.exception.usage.content, {})
        for values in ({'SB_MODEL_MODE':'demo'},
                       {'SB_MODEL_MODE':'local','SB_MODEL_NAME':'x','SB_MODEL_BASE_URL':'https://example.test'},
                       {'SB_MODEL_MODE':'provider','SB_MODEL_NAME':'x','SB_MODEL_PROVIDER':'unknown',
                        'SB_MODEL_BASE_URL':'https://example.test','SB_MODEL_API_KEY':'test-key'}):
            with self.assertRaises(ModelFailure):
                self.module.provider_from_settings(values).generate(self.request())
