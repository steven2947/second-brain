"""公开答案schema复用已锁定核心字段，仅裁剪私有引用并增加产品书目投影。"""
import copy
import json
from pathlib import Path


def _inline(value, definitions):
    """value为本地固定schema片段；definitions只解析同文件的内部引用，不访问网络。"""
    if isinstance(value, list):
        return [_inline(item, definitions) for item in value]
    if not isinstance(value, dict):
        return value
    if '$ref' in value:
        reference = value['$ref']
        if not reference.startswith('#/$defs/'):
            raise ValueError('公开schema不接受外部引用')
        return _inline(definitions[reference.removeprefix('#/$defs/')], definitions)
    return {key: _inline(item, definitions) for key, item in value.items()}


def content_schema():
    """无参数；输出与public_answer一致的公开结构，模型输出仍先经过原核心完整校验。"""
    root = Path(__file__).resolve().parents[2] / 'schemas'
    packet = json.loads((root / 'answer-packet.v3.schema.json').read_text(encoding='utf-8'))
    draft = json.loads((root / 'analysis-draft.v3.schema.json').read_text(encoding='utf-8'))
    properties = copy.deepcopy(packet['properties'])
    for name in ('session_id', 'library_version'):
        properties.pop(name)
    for name in set(properties) & set(draft['properties']):
        properties[name] = _inline(draft['properties'][name], draft.get('$defs', {}))
    witness = properties['witness_cards']['items']
    witness['properties'].pop('original_card_ref')
    witness['required'].remove('original_card_ref')
    source = properties['sources']['items']
    source['properties']['excerpt'] = {'type': ['string', 'null']}
    source['properties']['quote_available'] = {'type': 'boolean'}
    source['required'].append('quote_available')
    properties['books'] = {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
        'required': ['book_id', 'title', 'author_display'], 'properties': {
            'book_id': {'type': 'string'}, 'title': {'type': 'string'},
            'author_display': {'type': ['string', 'null']}}}}
    return _inline({'type': 'object', 'additionalProperties': False, 'properties': properties,
                    'required': list(properties)}, packet.get('$defs', {}))
