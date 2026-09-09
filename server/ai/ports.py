"""模型协议独立于HTTP、Django和数据库；未配置模式明确失败。"""
from dataclasses import dataclass
from typing import Callable, Protocol


class ModelFailure(Exception):
    """只携带固定错误代码，不把供应商原响应或私有上下文写入错误。"""

    def __init__(self, code, *, usage=None):
        """code为固定失败分类；usage可携带仅含实际元数据的Generation，不进入错误字符串。"""
        self.code = code
        self.usage = usage
        super().__init__(code)


@dataclass(frozen=True)
class GenerationRequest:
    """purpose/system/context/schema为服务端构造输入；deadline是单调时钟截止点。"""
    purpose: str
    system: str
    context: dict
    schema: dict
    deadline: float
    max_output_tokens: int
    cancelled: Callable[[], bool]


@dataclass(frozen=True)
class Generation:
    """content为结构化提案；model/provider与token只记录实际报告，缺失保持None。"""
    content: dict
    provider: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None


class Provider(Protocol):
    """部署者配置的唯一生成端口，不接受普通用户指定网络地址或工具权限。"""

    def generate(self, request: GenerationRequest) -> Generation:
        """request为一次受限生成请求；实现必须遵守截止时间与取消，不自行重试。"""
        ...


class DisabledProvider:
    """模型未配置时不返回演示答案，也不偷取其他工具凭据。"""

    def generate(self, request: GenerationRequest) -> Generation:
        """request不会发送给任何网络服务。"""
        raise ModelFailure('MODEL_UNAVAILABLE')
