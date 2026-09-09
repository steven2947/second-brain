"""正文结构及精确字符位置；纯函数，不修改来源文件。"""

import hashlib
import re
from src.knowledge.evidence import verify_span


def normalize_markdown(text, included_ranges):
    """按范围解析正文；text 保留原字符，included_ranges 用唯一标题给定半开区间。"""
    fingerprint = hashlib.sha256(text.encode('utf-8')).hexdigest()
    headings = list(re.finditer(r'^(#{1,6})[ \t]+([^\n\r]+?)[ \t]*\r?$', text, re.M))
    if not headings:
        raise ValueError('INVALID_ARGUMENT: 无标题，请先建立人工审核的范围清单')
    ranges = []
    for spec in included_ranges:
        positions = []
        for key in ('start_heading', 'end_heading'):
            title = spec[key]
            if title is None and key == 'end_heading':
                positions.append(len(text))
                continue
            matches = [h.start() for h in headings if h.group(2).strip() == title]
            if len(matches) != 1:
                raise ValueError(f'INVALID_ARGUMENT: 范围标题必须唯一存在：{title}')
            positions.append(matches[0])
        if positions[0] >= positions[1]:
            raise ValueError('INVALID_ARGUMENT: 范围顺序错误')
        ranges.append(tuple(positions))
    sections, excluded, paragraphs = [], [], []
    hierarchy = []
    for index, heading in enumerate(headings):
        start = heading.start()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        level, title = len(heading.group(1)), heading.group(2).strip()
        included = any(left <= start < right for left, right in ranges)
        # 完整标题栈供排除清单审计；正文只继承已纳入的祖先，不改原文层级或位置。
        hierarchy = [(lev, value, kept) for lev, value, kept in hierarchy if lev < level]
        hierarchy.append((level, title, included))
        identifier = f'section.{fingerprint[:12]}.{index:03d}'
        section = {'id': identifier, 'title': title, 'level': level,
                   'path': ' / '.join(value for _, value, _ in hierarchy), 'start': start, 'end': end}
        if not included:
            excluded.append({**section, 'reason': '不在已确认正文范围：前置材料、推荐书单、致谢或参考索引'})
            continue
        section['path'] = ' / '.join(value for _, value, kept in hierarchy if kept)
        section['paragraph_ids'] = []
        body_start = heading.end()
        for item in re.finditer(r'\S.*?(?=\r?\n[ \t]*\r?\n|\Z)', text[body_start:end], re.S):
            left = body_start + item.start()
            right = left + len(item.group().rstrip())
            paragraph = {'id': f'paragraph.{fingerprint[:12]}.{len(paragraphs):04d}',
                         'section_id': identifier, 'chapter': section['path'],
                         'start': left, 'end': right, 'text': text[left:right]}
            paragraphs.append(paragraph)
            section['paragraph_ids'].append(paragraph['id'])
        sections.append(section)
    if not paragraphs:
        raise ValueError('INVALID_ARGUMENT: 正文为空')
    return {'schema_version': 1, 'source_sha256': fingerprint, 'source_chars': len(text),
            'included_ranges': included_ranges, 'sections': sections,
            'excluded_sections': excluded, 'paragraphs': paragraphs}
