"""自编回环HTTP响应测试真实SSE流式传输；不是供应商或真实模型效果验收。"""
import importlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from django.test import SimpleTestCase
from ai.ports import GenerationRequest, ModelFailure


class ProviderTransportTests(SimpleTestCase):
    """只监听回环随机端口，检查SSE结构、增量拼接、重定向、取消与超时。"""

    def setUp(self):
        """无参数；不存在实现时先明确失败；测试服务器仅返回自编内容。"""
        self.assertTrue((Path(__file__).resolve().parents[1]/'ai/provider.py').exists(), '缺少模型传输')
        self.module = importlib.import_module('ai.provider')
        self.received = []
        self.events = [
            {'choices':[{'delta':{'role':'assistant'},'finish_reason':None}]},
            {'choices':[{'delta':{'content':'{"ok": true}'},'finish_reason':'stop'}]},
            {'choices':[],'usage':{'prompt_tokens':12,'completion_tokens':4},'model':'actual-test-model'},
        ]
        self.status, self.delay = 200, 0
        test = self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                """无参数；读取本测试POST并按测试配置发送自编SSE响应。"""
                test.received.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length']))), dict(self.headers)))
                if test.delay:
                    threading.Event().wait(test.delay)
                self.send_response(test.status)
                self.send_header('Content-Type','text/event-stream')
                if test.status == 302:
                    self.send_header('Location', '/must-not-follow')
                self.end_headers()
                try:
                    for event in test.events:
                        self.wfile.write(b'data: ' + json.dumps(event).encode() + b'\n\n')
                    self.wfile.write(b'data: [DONE]\n\n')
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
        """无参数；执行真实SSE POST，解析供应商报告而非配置模型名猜测计量。"""
        result = self.provider.generate(self.request())
        self.assertEqual(result.content, {'ok':True})
        self.assertEqual((result.input_tokens,result.output_tokens,result.model),(12,4,'actual-test-model'))
        path,body,headers = self.received[0]
        self.assertEqual(path,'/v1/chat/completions')
        self.assertEqual(json.loads(body['messages'][1]['content'])['message'],'  原话\n')
        self.assertEqual(body['max_tokens'],60)
        self.assertTrue(body['stream'])
        self.assertNotIn('Authorization',headers)

    def test_content_deltas_accumulate_across_chunks(self):
        """无参数；内容分多个增量到达时按序拼接。"""
        self.events = [
            {'choices':[{'delta':{'content':'{"ok"'},'finish_reason':None}]},
            {'choices':[{'delta':{'content ':': true}'},'finish_reason':None}]},
            {'choices':[{'delta':{},'finish_reason':'stop'}]},
        ]
        self.events[1]['choices'][0]['delta'] = {'content':': true}'}
        result = self.provider.generate(self.request())
        self.assertEqual(result.content, {'ok':True})

    def test_unknown_usage_stays_unknown(self):
        """无参数；供应商未报告token时不可填0。"""
        self.events = [event for event in self.events if 'usage' not in event]
        result = self.provider.generate(self.request())
        self.assertIsNone(result.input_tokens)
        self.assertIsNone(result.output_tokens)

    def test_redirect_and_private_error_are_not_followed_or_exposed(self):
        """无参数；既不重发也不回显原始供应商错误。"""
        self.status,self.events = 302,[{'private':'secret test detail'}]
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
        self.events[-2]['choices'][0]['finish_reason'] = 'length'
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
