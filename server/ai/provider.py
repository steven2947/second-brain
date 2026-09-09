"""受配置控制的JSON模型传输；无自动重试、环境代理、重定向或演示回退。"""
import asyncio
import json
import time
from urllib.parse import urlsplit

import httpx
from .ports import DisabledProvider, Generation, ModelFailure


def _check(request):
    """request为服务端请求；取消和整体截止点优先于网络继续等待。"""
    if request.cancelled():
        raise ModelFailure('RUN_CANCELLED')
    if time.monotonic() >= request.deadline:
        raise ModelFailure('RUN_TIMEOUT')


def _unique(pairs):
    """pairs为JSON对象键值；重复字段不能成为模糊提案。"""
    result = {}
    for key,value in pairs:
        if key in result:
            raise ValueError('duplicate')
        result[key] = value
    return result


def _unwrap_fenced(text):
    """有界正文若被Markdown代码栏整体包裹则剥去；不是代码栏则原样返回。"""
    stripped = text.strip()
    if not (stripped.startswith('```') and stripped.endswith('```')):
        return text
    inner = stripped[3:-3].strip()
    if inner[:4].lower() == 'json':
        inner = inner[4:]
    return inner.strip()


def _constant(value):
    """value为非JSON常量；拒绝NaN等无效内容。"""
    raise ValueError('invalid constant')


def _json(value):
    """value为有界响应文本，解析错误仅在外层映射固定码。"""
    return json.loads(value, object_pairs_hook=_unique, parse_constant=_constant)


def _tokens(value):
    """value只来自供应商usage；缺失为None，不估算。"""
    if value is not None and (type(value) is not int or not 0 <= value <= 9223372036854775807):
        raise ValueError('invalid usage')
    return value


class JSONProvider:
    """固定chat-completions协议，配置来自部署者，不接普通用户的地址或密钥。"""

    def __init__(self, base_url, model, *, provider, key=None, extra_body=None):
        """base_url/model/provider/key由工厂先核验；私有key不进入repr或日志。
        extra_body为部署者经SB_MODEL_EXTRA_JSON显式配置的固定额外字段（如供应商开关）。"""
        self.url = base_url.rstrip('/')+'/chat/completions'
        self.model, self.provider, self._key = model, provider, key
        self._extra_body = extra_body if isinstance(extra_body, dict) else None

    def generate(self, request):
        """request含结构与截止点；同步worker调用异步有界传输，不跨线程传数据库连接。"""
        _check(request)
        if (type(request.max_output_tokens) is not int or not 1 <= request.max_output_tokens <= 32768):
            raise ModelFailure('INVALID_INPUT')
        try:
            return asyncio.run(self._generate(request))
        except ModelFailure:
            raise
        except httpx.TimeoutException:
            raise ModelFailure('RUN_TIMEOUT') from None
        except (httpx.HTTPError, OSError):
            raise ModelFailure('MODEL_UNAVAILABLE') from None
        except (ValueError,TypeError,KeyError,IndexError,AttributeError,RecursionError):
            raise ModelFailure('MODEL_OUTPUT_INVALID') from None

    async def _generate(self, request):
        """request为一次生成；独立观察取消信号，退出时取消底层HTTP任务。"""
        task = asyncio.create_task(self._post(request))
        try:
            while not task.done():
                _check(request)
                await asyncio.wait({task},timeout=min(0.05,max(0.001,request.deadline-time.monotonic())))
            _check(request)
            return task.result()
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task,return_exceptions=True)

    async def _post(self, request):
        """request仅传原数据和服务端schema；成功与错误响应均不记录正文。"""
        budget = max(0.001,request.deadline-time.monotonic())
        payload = {'model':self.model,'messages':[
            {'role':'system','content':request.system+'\n只返回符合以下JSON Schema的JSON对象，直接输出JSON本身，不要用Markdown代码栏或任何文字包裹：\n'+json.dumps(request.schema,ensure_ascii=False)},
            {'role':'user','content':json.dumps(request.context,ensure_ascii=False)}],
            'response_format':{'type':'json_object'},'max_tokens':request.max_output_tokens,'stream':False}
        if self._extra_body:
            payload.update(self._extra_body)
        body = json.dumps(payload,ensure_ascii=False,allow_nan=False).encode()
        if len(body)>2*1024*1024:
            raise ModelFailure('INVALID_INPUT')
        headers = {'Content-Type':'application/json','Accept':'application/json'}
        if self._key:
            headers['Authorization'] = 'Bearer '+self._key
        async with httpx.AsyncClient(timeout=httpx.Timeout(budget,connect=min(10,budget)),
                                     trust_env=False,follow_redirects=False) as client:
            async with client.stream('POST',self.url,headers=headers,content=body) as response:
                if response.status_code != 200:
                    raise ModelFailure('MODEL_UNAVAILABLE')
                chunks,size = [],0
                async for chunk in response.aiter_bytes():
                    _check(request)
                    size += len(chunk)
                    if size>2*1024*1024:
                        raise ModelFailure('MODEL_OUTPUT_INVALID')
                    chunks.append(chunk)
        value = _json(b''.join(chunks))
        usage = value.get('usage') or {}
        model = value.get('model')
        if model is not None and (not isinstance(model,str) or not 1<=len(model)<=240):
            raise ModelFailure('MODEL_OUTPUT_INVALID')
        reported = Generation(content={},provider=self.provider,model=model,
            input_tokens=_tokens(usage.get('prompt_tokens')),output_tokens=_tokens(usage.get('completion_tokens')),
            cached_tokens=_tokens((usage.get('prompt_tokens_details') or {}).get('cached_tokens')))
        try:
            choices = value['choices']
            if not isinstance(choices,list) or len(choices)!=1 or choices[0].get('finish_reason')!='stop':
                raise ValueError('invalid choices')
            message = choices[0]['message']
            if message.get('tool_calls') or message.get('refusal'):
                raise ValueError('unexpected tools')
            content = _json(_unwrap_fenced(message['content']))
            if not isinstance(content,dict):
                raise ValueError('invalid content')
        except (ValueError,TypeError,KeyError,IndexError,AttributeError,RecursionError):
            # 已报告的实际用量不能因正文无效而丢弃；错误不携带正文或提示词。
            raise ModelFailure('MODEL_OUTPUT_INVALID', usage=reported) from None
        return Generation(content=content,provider=reported.provider,model=reported.model,
            input_tokens=reported.input_tokens,output_tokens=reported.output_tokens,cached_tokens=reported.cached_tokens)


def provider_from_settings(values=None):
    """values为空时仅读本项目Django设置；显式字典供受控配置和测试，不来自HTTP输入。"""
    if values is None:
        from django.conf import settings
        values = {name:getattr(settings,name,None) for name in ('SB_MODEL_MODE','SB_MODEL_BASE_URL',
            'SB_MODEL_NAME','SB_MODEL_PROVIDER','SB_MODEL_API_KEY')}
    mode = values.get('SB_MODEL_MODE','disabled')
    if mode == 'disabled':
        return DisabledProvider()
    if mode not in ('local','provider'):
        raise ModelFailure('MODEL_UNAVAILABLE')
    base,model = values.get('SB_MODEL_BASE_URL'),values.get('SB_MODEL_NAME')
    if not isinstance(base,str) or not isinstance(model,str) or not model.strip() or len(model)>240:
        raise ModelFailure('MODEL_UNAVAILABLE')
    url = urlsplit(base)
    if (not url.hostname or url.username is not None or url.password is not None or url.query or url.fragment
            or any(char in base for char in ('\r','\n','\\'))):
        raise ModelFailure('MODEL_UNAVAILABLE')
    key = None
    if mode == 'local':
        if url.scheme not in ('http','https') or url.hostname not in ('localhost','127.0.0.1','::1'):
            raise ModelFailure('MODEL_UNAVAILABLE')
    else:
        key = values.get('SB_MODEL_API_KEY')
        if (url.scheme!='https' or values.get('SB_MODEL_PROVIDER')!='openai-compatible'
                or not isinstance(key,str) or not key.strip() or '\r' in key or '\n' in key):
            raise ModelFailure('MODEL_UNAVAILABLE')
    return JSONProvider(base,model,provider='local' if mode=='local' else 'openai-compatible',key=key,
        extra_body=_extra_body_from_env())


def _extra_body_from_env():
    """读取部署者显式配置的额外请求字段；配置存在但非法时拒绝启动生成。"""
    import os
    raw = os.environ.get('SB_MODEL_EXTRA_JSON')
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except ValueError:
        raise ModelFailure('MODEL_UNAVAILABLE') from None
    if not isinstance(value,dict) or not all(isinstance(k,str) for k in value):
        raise ModelFailure('MODEL_UNAVAILABLE')
    return value
