"""同一公开结构的Markdown表达；不再次让模型增补主张或导入内部提示词。"""
import hashlib
import html
import json
import re


def packet_hash(packet):
    """packet为已校验私有包；规范JSON计算内容指纹，不作为用户身份凭据。"""
    return hashlib.sha256(json.dumps(packet, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _text(value):
    """value为公开语义字符串；禁用原始HTML和模型自行注入的Markdown链接/图片。"""
    return re.sub(r'([\\`*_{}\[\]()#+.!|>~\-])', r'\\\1', html.escape(str(value), quote=False))


def render_markdown(payload):
    """payload为当前许可投影；先建议与行动，再原理/分歧/依据，最后留下明确续聊指令。"""
    verdict, parts = payload['verdict'], []
    parts.extend(['## 建议先这样做', _text(verdict['conclusion']), _text(verdict['reasoning_summary'])])
    for index, action in enumerate(payload['actions'], 1):
        parts.extend([f"### {index}. {_text(action['step'])}",
            f"完成标准：{_text(action['completion_criteria'])}",
            f"观察信号：{_text(action['validation_signal'])}",
            f"停止或调整：{_text(action['stop_condition'])}"])
    for synthesis in payload['system_syntheses']:
        parts.extend([f"### 系统综合：{_text(synthesis['title'])}", _text(synthesis['content']),
                      f"还要验证：{_text(synthesis['validation_needed'])}"])
    framing = payload['problem_framing']
    parts.extend(['## 这次真正要分析什么', _text(framing['reframed_question']), _text(framing['diagnostic_summary'])])
    for label, values in (('关键未知', framing['key_uncertainties']), ('待验证前提', framing['hidden_assumptions'])):
        parts.extend(f'{label}：{_text(value)}' for value in values)
    parts.append('## 采用了哪些书与知识')
    parts.extend(f"- 《{_text(book['title'])}》 · {_text(book['author_display'] or '作者信息未提供')}"
                 for book in payload['books'])
    ledger = payload['call_ledger']
    parts.append(f"检索范围 {len(ledger['books_searched'])} 本；形成候选 {len(ledger['candidates'])} 张；实际采用 {len(ledger['admitted'])} 张。检索范围不等于全部采用。")
    for witness in payload['witness_cards']:
        parts.extend([f"### 《{_text(witness['book_title'])}》 · {_text(witness['author'] or '作者信息未提供')}",
            f"本次采用：{_text(witness['adopted_claim'])}", f"原理：{_text(witness['principle'])}",
            f"如何起作用：{_text(witness['mechanism'])}",
            f"对应你的情况：{_text(witness['situation_mapping'])}",
            f"独立判断：{_text(witness['independent_judgment'])}",
            f"如何改变建议：{_text(witness['judgment_effect'])}"])
        for label, key in (('前提', 'assumptions'), ('不适用条件', 'non_applicable_conditions'),
                           ('误用风险', 'misuse_risks'), ('本次不采用', 'excluded_scope')):
            parts.extend(f'{label}：{_text(value)}' for value in witness[key])
    for group in payload['knowledge_groups']:
        parts.extend([f"### 知识如何组合：{_text(group['title'])}", _text(group['purpose']), _text(group['synthesis'])])
    parts.append('## 圆桌：独立立场与交叉检验')
    for key, label in (('support', '支持方'), ('opposition', '反方'), ('alternative', '替代路线'), ('evidence_audit', '证据审查')):
        seat = payload['roundtable'][key]
        suffix = '（材料缺口）' if seat['status'] == 'gap' else ''
        parts.extend([f'### {label}{suffix}', _text(seat['claim'])])
    for relation in payload['argument_relations']:
        parts.extend([_text(relation['to_claim']), _text(relation['explanation'])])
    for label, values in (('共识', verdict['consensus']), ('仍有分歧', verdict['disagreements']),
                           ('不确定性', verdict['uncertainties']), ('何时改判', verdict['change_conditions'])):
        parts.extend(f'{label}：{_text(value)}' for value in values)
    parts.append('## 依据来源')
    for source in payload['sources']:
        parts.append(f"《{_text(source['book_title'])}》 · {_text(source['author'] or '作者信息未提供')} · {_text(source['chapter'])}")
        parts.append(_text(source['excerpt']) if source['excerpt'] is not None else '当前许可不提供原文短引。')
    parts.append('## 可以带走的方法')
    for item in payload['learning_takeaways']:
        parts.extend([_text(item['method']), _text(item['how_to_reuse'])])
    parts.append('## 下一步继续聊什么')
    for option in payload['continuation_options']:
        parts.extend([_text(option['title']), _text(option['description'])])
    parts.extend([_text(payload['next_chat_action']['reason']),
                  '继续和 AI 聊：' + _text(payload['next_chat_action']['prompt'])])
    return '\n\n'.join(parts)
