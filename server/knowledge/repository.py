"""单知识版本公开查询；授权短事务包围固定文件读取，返回前完整复核。"""
from django.db import connection
from access.services import KnowledgeError, access_snapshot, authorized_release_ids, not_found
from knowledge.projections import book_payload, book_detail, browse_card, source_preview, card_summary
from knowledge.release_loader import ReleaseUnavailable, load_release
from src.retrieval.search import SearchEngine


class KnowledgeRepository:
    """可信登录用户的请求级仓库；不持有授权缓存或跨版本搜索状态。"""

    def __init__(self, user):
        """user为认证层提供的Django用户，不接收客户端owner或文件路径。"""
        self.user = user

    def _read(self, release_id, project):
        """release_id为公开版本ID；project将已核验Library物化为白名单字典。"""
        if connection.in_atomic_block or not connection.get_autocommit():
            raise KnowledgeError('RELEASE_UNAVAILABLE', '知识版本暂不可用', 503)
        before = access_snapshot(self.user, release_id)
        release = before['release']
        try:
            library = load_release(release['storage_key'], release['source_fingerprint'], release['content_version'])
            if (set(before['books']) != {book['id'] for book in library.manifest['books']}
                    or len(library.manifest['books']) != release['book_count']
                    or len(library.cards) != release['card_count']):
                raise ReleaseUnavailable()
            for book in library.manifest['books']:
                book_payload(book)
            result = project(library, before)
        except KnowledgeError:
            raise
        except (ReleaseUnavailable, ValueError, KeyError, TypeError, OSError):
            raise KnowledgeError('RELEASE_UNAVAILABLE', '知识版本暂不可用', 503) from None
        if access_snapshot(self.user, release_id) != before:
            raise not_found()
        return result

    def list_books(self, release_id):
        """release_id为已授权固定版本；返回完整物化书目，由HTTP层执行有界分页。"""
        return self._read(release_id, lambda library, snapshot: {
            'release_id': str(snapshot['release']['id']), 'content_version': library.version,
            'items': [book_payload(book) for book in sorted(library.manifest['books'], key=lambda book: book['id'])]})

    def list_releases(self):
        """无参数；只枚举本人有效grant并两次检查整库browse许可，不读取未授权文件。"""
        snapshots, items = [], []
        for release_id in authorized_release_ids(self.user):
            try:
                snapshot = access_snapshot(self.user, release_id)
            except KnowledgeError:
                continue
            release, collection = snapshot['release'], snapshot['collection']
            items.append({'id': str(release_id), 'library_id': str(collection['id']),
                'title': collection['title'], 'description': collection['description'],
                'content_version': release['content_version'], 'book_count': release['book_count'],
                'card_count': release['card_count']})
            snapshots.append((release_id, snapshot))
        for release_id, before in snapshots:
            if access_snapshot(self.user, release_id) != before:
                raise not_found()
        return {'items': items}

    def list_cards(self, release_id, *, q='', book='', author='', card_type=''):
        """release_id为版本ID；q为关键词，book仅书ID，author支持ID/名称，card_type为kind。"""
        def project(library, snapshot):
            """library为已授权固定库，snapshot为本次授权快照；BM25只保留真实正分匹配。"""
            books = {item['id']: item for item in library.manifest['books']}
            scores = SearchEngine(library).keyword_scores(q) if q else {}
            cards = [card for card in library.cards.values()
                if (not q or scores[card['id']] > 0)
                and (not book or card['book_id'] == book)
                and (not author or author in (card['author_id'], books[card['book_id']].get('author')))
                and (not card_type or card['kind'] == card_type)]
            cards.sort(key=lambda card: (-scores.get(card['id'], 0), card['id']))
            return {'release_id': str(snapshot['release']['id']), 'content_version': library.version,
                    'items': [card_summary(card, books[card['book_id']], snapshot['release']['id']) for card in cards]}
        return self._read(release_id, project)

    def get_book(self, release_id, book_id):
        """release_id为版本ID，book_id为该版本内书目ID；返回章节覆盖及元数据缺口。"""
        return self._read(release_id, lambda library, snapshot: book_detail(library, snapshot, book_id))

    def get_card(self, release_id, card_id):
        """release_id为版本ID，card_id为整理卡ID；不将浏览内容当成本次采用主张。"""
        return self._read(release_id, lambda library, snapshot: browse_card(library, snapshot, card_id))

    def get_evidence(self, release_id, evidence_id):
        """release_id为版本ID，evidence_id为原文证据ID；必须额外获得所属书quote许可。"""
        return self._read(release_id, lambda library, snapshot: source_preview(library, snapshot, evidence_id))
