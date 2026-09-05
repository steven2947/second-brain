"""证据字符范围与来源指纹规则，独立于导入和命令行。"""
import hashlib


def verify_span(text, source_sha256, start, end, excerpt):
    """text 为来源；source_sha256、start/end 与 excerpt 为待核对的指纹、字符范围及片段。"""
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != source_sha256:
        raise ValueError('SOURCE_VERSION_MISMATCH: 来源指纹改变')
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
        raise ValueError('INVALID_ARGUMENT: 证据字符范围无效')
    if text[start:end] != excerpt:
        raise ValueError('INVALID_EVIDENCE: 原文与片段不一致')
