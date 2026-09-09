"""获准书库的只读HTTP接线；不接收文件路径或自行赋予权限。"""
from . import serializers as dto
from .http import page_result, read_endpoint


@read_endpoint(dto.PageQuerySerializer, dto.LibraryPageSerializer)
def libraries(request, user, query):
    """request为HTTP请求，user来自session，query为分页字段。"""
    from .repository import KnowledgeRepository
    return page_result(KnowledgeRepository(user).list_releases(), user, query, 'libraries')


@read_endpoint(dto.BookQuerySerializer, dto.BookPageSerializer)
def books(request, user, query, release_id):
    """release_id为固定版本UUID；书目过滤只能在授权仓库返回后执行。"""
    from .repository import KnowledgeRepository
    result = KnowledgeRepository(user).list_books(release_id)
    result['items'] = [book for book in result['items']
        if (not query['q'] or query['q'].casefold() in book['title'].casefold())
        and (not query['author'] or query['author'] == book['author_display'])]
    return page_result(result, user, query, 'books')


@read_endpoint(dto.DetailQuerySerializer, dto.BookDetailSerializer)
def book(request, user, query, release_id, book_id):
    """release_id/book_id只作为知识ID查询，不作为磁盘路径。"""
    from .repository import KnowledgeRepository
    return KnowledgeRepository(user).get_book(release_id, book_id)


@read_endpoint(dto.CardQuerySerializer, dto.CardPageSerializer)
def cards(request, user, query, release_id):
    """release_id为版本，query为已验证关键词及过滤器；检索先鉴权。"""
    from .repository import KnowledgeRepository
    result = KnowledgeRepository(user).list_cards(release_id, q=query['q'], book=query['book'],
        author=query['author'], card_type=query['type'])
    return page_result(result, user, query, 'cards')


@read_endpoint(dto.DetailQuerySerializer, dto.BrowseCardSerializer)
def card(request, user, query, release_id, card_id):
    """card_id为当前获准版本的卡片ID；原卡浏览不代表采用。"""
    from .repository import KnowledgeRepository
    return KnowledgeRepository(user).get_card(release_id, card_id)


@read_endpoint(dto.DetailQuerySerializer, dto.SourcePreviewSerializer)
def evidence(request, user, query, release_id, evidence_id):
    """evidence_id为证据ID；只能取得额外获准的短引。"""
    from .repository import KnowledgeRepository
    return KnowledgeRepository(user).get_evidence(release_id, evidence_id)
