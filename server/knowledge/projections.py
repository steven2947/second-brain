"""固定核心记录到公开字段白名单；禁止直接序列化ORM或原卡。"""
from access.services import not_found


def book_payload(book):
    """book为已验证manifest书目；作者未知保持空值，不使用旧数据库展示投影猜测。"""
    if not isinstance(book.get('title'), str) or not book['title'].strip():
        raise ValueError('无效书目')
    author = book.get('author')
    if author is not None and not isinstance(author, str):
        raise ValueError('无效作者')
    author = author if isinstance(author, str) and author.strip() else None
    return {'id': book['id'], 'title': book['title'], 'author_display': author,
            'metadata_status': 'verified' if author else 'partial'}


def books_by_id(library):
    """library为已验证固定核心库；书目只从manifest构造。"""
    return {book['id']: book for book in library.manifest['books']}


def card_summary(card, book, release_id):
    """card为核心卡，book为同版本manifest中对应书目，release_id为服务端确认版本ID。"""
    return {'release_id': str(release_id), 'card_id': card['id'],
            'book': book_payload(book),
            'type': card['kind'], 'title': card['title'], 'statement': card['statement']}


def source_preview(library, snapshot, evidence_id):
    """library为固定库，snapshot含逐书短引许可，evidence_id仅作字典ID查询。"""
    evidence = library.evidence.get(evidence_id)
    if evidence is None or evidence['book_id'] not in snapshot['quotes']:
        raise not_found()
    evidence = library.get_evidence(evidence_id, context=0)
    text = evidence['text'][:snapshot['quotes'][evidence['book_id']]]
    origin = evidence.get('origin')
    position = origin if origin else evidence
    location = {'kind': 'original' if origin else 'evidence_compilation',
                'start': position['start'], 'end': position['start'] + len(text),
                'paragraph_id': origin.get('paragraph_id') if origin else None,
                'notice': '原书字符位置，非页码' if origin else '证据汇编字符位置，非原书页码'}
    return {'release_id': str(snapshot['release']['id']), 'evidence_id': evidence['id'],
            'book': book_payload(books_by_id(library)[evidence['book_id']]),
            'chapter': evidence['chapter'], 'text': text,
            'truncated': len(text) < len(evidence['text']), 'location': location}


def browse_card(library, snapshot, card_id):
    """library/snapshot属于同一授权版本；card_id为待浏览核心卡ID。"""
    card = library.cards.get(card_id)
    if card is None:
        raise not_found()
    result = card_summary(card, books_by_id(library)[card['book_id']], snapshot['release']['id'])
    explanation = card.get('reasoning', '')
    related = []
    for edge in library.edges:
        if card_id not in (edge['from'], edge['to']):
            continue
        relation = {key: edge[key] for key in ('id', 'from', 'to', 'type', 'basis', 'rationale')}
        if edge['basis'] == 'inference':
            relation['rationale'] = '系统推断：' + relation['rationale']
        related.append(relation)
    sources = [source_preview(library, snapshot, identifier) for identifier in card['evidence_ids']
               if library.evidence[identifier]['book_id'] in snapshot['quotes']]
    gaps = []
    if not explanation:
        gaps.append('未提供原理说明')
    if not card.get('source_claim_type'):
        gaps.append('未标明来源主张归属')
    if not sources:
        gaps.append('当前许可不提供原文预览')
    return {**result, 'explanation': explanation,
            **{field: list(card.get(field, [])) for field in
               ('conditions', 'boundaries', 'steps')},
            'application_notes': card.get('application_notes', ''),
            'source_claim_type': card.get('source_claim_type', 'unknown'),
            'related': related, 'source_previews': sources,
            'usage_notice': '整理内容，未针对当前问题采用', 'gaps': gaps}


def book_detail(library, snapshot, book_id):
    """library/snapshot为已授权固定版本；book_id为书目ID，章节仅汇总已有证据。"""
    book = books_by_id(library).get(book_id)
    if book is None:
        raise not_found()
    payload = book_payload(book)
    gaps = ['章节仅来自已有证据，不代表全书目录']
    if payload['author_display'] is None:
        gaps.append('作者信息未提供')
    return {**payload, 'release_id': str(snapshot['release']['id']),
            'content_version': library.version,
            'chapters': list(dict.fromkeys(evidence['chapter'] for evidence in library.evidence.values()
                                          if evidence['book_id'] == book_id)), 'gaps': gaps}
