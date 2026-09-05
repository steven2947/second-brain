"""知识库验证、不可变版本发布及证据/图谱查询。"""

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from src.knowledge.evidence import verify_span


def read_json(path):
    """读取 JSON；path 为明确的本地文件位置。"""
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load_records(path):
    """按唯一 ID 读取记录；path 为卡片或证据目录。"""
    records = {}
    for filename in sorted(Path(path).glob('*.json')):
        item = read_json(filename)
        identifier = item.get('id')
        if not isinstance(identifier, str) or not identifier or identifier in records:
            raise ValueError('INVALID_LIBRARY: 缺失或重复 ID')
        records[identifier] = item
    if not records:
        raise ValueError('INVALID_LIBRARY: 记录为空')
    return records


def content_version(path):
    """计算知识目录指纹；path 下每个文件名及字节均参与，拒绝符号链接。"""
    digest = hashlib.sha256()
    path = Path(path)
    for file in sorted(path.rglob('*')):
        if file.is_symlink():
            raise ValueError('INVALID_LIBRARY: 不接受符号链接')
        if file.is_file():
            digest.update(file.relative_to(path).as_posix().encode())
            digest.update(b'\0')
            digest.update(file.read_bytes())
            digest.update(b'\0')
    return digest.hexdigest()[:24]


def validate_library(path):
    """验证书库；path 为单个版本目录，结构验证不等于语义审计。"""
    path = Path(path).resolve()
    content_version(path)
    manifest = read_json(path / 'manifest.json')
    if manifest.get('schema_version') != 1 or not manifest.get('books'):
        raise ValueError('INVALID_LIBRARY: 清单版本或书籍无效')
    books = {book['id']: book for book in manifest['books']}
    if len(books) != len(manifest['books']):
        raise ValueError('INVALID_LIBRARY: 书籍 ID 重复')
    cards, evidence = load_records(path / 'cards'), load_records(path / 'evidence')
    graph = read_json(path / 'relations.json')
    from jsonschema import Draft202012Validator
    schema_root = Path(__file__).resolve().parents[2] / 'schemas'
    for filename, items in [('knowledge-card.schema.json', cards.values()),
                            ('evidence.schema.json', evidence.values()), ('relations.schema.json', [graph])]:
        validator = Draft202012Validator(read_json(schema_root / filename))
        for item in items:
            error = next(validator.iter_errors(item), None)
            if error:
                raise ValueError(f'INVALID_LIBRARY: {error.message}')
    source_cache = {}
    for ev in evidence.values():
        source = (path / ev['source_path']).resolve()
        if Path(ev['source_path']).is_absolute() or not source.is_relative_to(path):
            raise ValueError('INVALID_LIBRARY: 来源路径越界')
        if ev['book_id'] not in books:
            raise ValueError('INVALID_LIBRARY: 证据所属书不存在')
        if source not in source_cache:
            source_cache[source] = source.read_bytes().decode('utf-8')
        verify_span(source_cache[source], ev['source_sha256'], ev['start'], ev['end'], ev['text'])
        if origin := ev.get('origin'):
            book = books[ev['book_id']]
            fingerprint = book.get('source_sha256')
            if (origin['source_sha256'] != fingerprint or not isinstance(fingerprint,str)
                or not re.fullmatch(r'paragraph\.'+fingerprint[:12]+r'\.\d+',origin['paragraph_id'])
                or ev['id'] != 'evidence.'+origin['paragraph_id']
                or not 0 <= origin['start'] < origin['end']
                or origin['end']-origin['start'] != len(ev['text'])
                or origin['end'] > book.get('source_chars',origin['end'])):
                raise ValueError('INVALID_LIBRARY: 原书来源映射无效')
    for card in cards.values():
        book = books.get(card['book_id'])
        if not book or card['author_id'] != book['author_id']:
            raise ValueError('INVALID_LIBRARY: 知识书籍/作者归属无效')
        for identifier in card['evidence_ids']:
            if identifier not in evidence or evidence[identifier]['book_id'] != card['book_id']:
                raise ValueError('INVALID_LIBRARY: 知识证据引用无效')
        supported = {evidence[key].get('origin',{}).get('paragraph_id') for key in card['evidence_ids']}
        if any(case['paragraph_id'] not in supported for case in card.get('source_cases',[])):
            raise ValueError('INVALID_LIBRARY: 书中案例没有对应证据')
    seen = set()
    for edge in graph['edges']:
        if edge['id'] in seen or edge['from'] not in cards or edge['to'] not in cards:
            raise ValueError('INVALID_LIBRARY: 图谱端点或 ID 无效')
        if any(identifier not in evidence for identifier in edge['evidence_ids']):
            raise ValueError('INVALID_LIBRARY: 关系证据无效')
        seen.add(edge['id'])
    return {'books': len(books), 'cards': len(cards), 'evidence': len(evidence), 'relations': len(seen)}


def publish_library(candidate, root):
    """验证后原子发布；candidate 为候选目录，root 为版本库根目录，失败保留 CURRENT。"""
    candidate, root = Path(candidate), Path(root)
    validate_library(candidate)
    version = content_version(candidate)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / '.publish.lock'
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise ValueError('LIBRARY_BUSY: 另一个发布任务持有锁') from exc
    temporary = None
    try:
        versions = root / 'versions'; versions.mkdir(exist_ok=True)
        target = versions / version
        previous = (root / 'CURRENT').read_text().strip() if (root / 'CURRENT').exists() else None
        if not target.exists():
            temporary = Path(tempfile.mkdtemp(prefix='.candidate-', dir=root))
            shutil.copytree(candidate, temporary / 'content')
            validate_library(temporary / 'content')
            if content_version(temporary / 'content') != version:
                raise ValueError('SOURCE_VERSION_MISMATCH: 发布期间候选改变')
            os.replace(temporary / 'content', target)
        elif content_version(target) != version:
            raise ValueError('INVALID_LIBRARY: 已发布版本被修改')
        pointer = root / '.CURRENT.pending'
        pointer.write_text(version + '\n', encoding='utf-8')
        os.replace(pointer, root / 'CURRENT')
        return {'version': version, 'previous': previous, 'reused': previous == version}
    finally:
        if temporary:
            shutil.rmtree(temporary)
        lock.rmdir()


class Library:
    """以只读方式提供书籍、知识、证据和有向图查询。"""

    def __init__(self, root):
        """root 为版本库或已解包的单版本目录；实例固定在打开时的版本。"""
        root = Path(root).resolve()
        if (root / 'CURRENT').is_file():
            version = (root / 'CURRENT').read_text().strip()
            if not re.fullmatch('[0-9a-f]{24}', version):
                raise ValueError('INVALID_LIBRARY: CURRENT 无效')
            root = root / 'versions' / version
            if content_version(root) != version:
                raise ValueError('SOURCE_VERSION_MISMATCH: 已发布知识文件变化')
        elif not (root / 'manifest.json').is_file():
            raise ValueError('LIBRARY_NOT_READY: 尚无已发布知识库')
        validate_library(root)
        self.root = root
        self.version = content_version(root)
        self.manifest = read_json(root / 'manifest.json')
        self.cards = load_records(root / 'cards')
        self.evidence = load_records(root / 'evidence')
        self.edges = read_json(root / 'relations.json')['edges']

    def list_books(self, author=None):
        """列出覆盖书目；author 可按作者 ID 或名称过滤。"""
        return [book for book in self.manifest['books'] if not author or author in (book['author_id'], book.get('author'))]

    def get_knowledge(self, identifier):
        """按 identifier 获取完整卡片；未知 ID 明确失败。"""
        if identifier not in self.cards:
            raise ValueError('NOT_FOUND: 知识 ID 不存在')
        return self.cards[identifier]

    def get_evidence(self, identifier, context=0):
        """读取证据与字符上下文；identifier 为证据 ID，context 限制在 0 至 2000。"""
        if type(context) is not int or not 0 <= context <= 2000:
            raise ValueError('INVALID_ARGUMENT: context 应为 0..2000')
        if identifier not in self.evidence:
            raise ValueError('NOT_FOUND: 证据 ID 不存在')
        ev = self.evidence[identifier]
        text = (self.root / ev['source_path']).read_bytes().decode('utf-8')
        verify_span(text, ev['source_sha256'], ev['start'], ev['end'], ev['text'])
        book = next(book for book in self.manifest['books'] if book['id'] == ev['book_id'])
        return {**ev, 'book_title': book['title'], 'context_text': text[max(0, ev['start']-context):ev['end']+context],
                'context_scope': '证据汇编中的相邻文本；原书位置以 origin 为准',
                'file': str(self.root / ev['source_path'])}

    def get_related(self, identifier, relation_type=None, hops=1, direction='both'):
        """有界展开关系；identifier 为卡片 ID，hops 为 1..3，direction 为 out/in/both。"""
        self.get_knowledge(identifier)
        if type(hops) is not int or not 1 <= hops <= 3 or direction not in ('out', 'in', 'both'):
            raise ValueError('INVALID_ARGUMENT: 关系展开参数无效')
        frontier, seen, emitted, result = {identifier}, {identifier}, set(), []
        for depth in range(1, hops + 1):
            next_frontier = set()
            for edge in self.edges:
                if edge['id'] in emitted or (relation_type and edge['type'] != relation_type):
                    continue
                other = None
                if direction in ('out', 'both') and edge['from'] in frontier:
                    other = edge['to']
                elif direction in ('in', 'both') and edge['to'] in frontier:
                    other = edge['from']
                if other:
                    result.append({'edge': edge, 'target': self.cards[other], 'depth': depth})
                    emitted.add(edge['id'])
                    if other not in seen:
                        next_frontier.add(other)
            seen.update(next_frontier); frontier = next_frontier
        return result
