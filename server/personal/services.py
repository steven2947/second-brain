"""本人记录短事务服务；磁盘校验和答案投影均在写事务外完成。"""
from django.core import signing
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError
from access.context import owner_transaction
from access.services import access_snapshot, analysis_snapshot, KnowledgeError
from answers.models import Answer
from answers.services import get_answer
from knowledge.repository import KnowledgeRepository
from problems.services import _current_user, _get, _uuid, invalid, not_found, unavailable, ProblemError
from .models import Bookmark, ActionRecord, Feedback
from .serializers import SaveBookmarkSerializer, CreateActionSerializer, UpdateActionSerializer, CreateFeedbackSerializer

ACTION_FIELDS = ('step', 'completion_criteria', 'validation_signal', 'stop_condition')


def _validate(serializer_class, data):
    """serializer_class为入口白名单；data为原始或HTTP已解析的数据，服务直调也验证。"""
    # HTTP的UUID字段已转换，恢复文本供同一严格输入契约再次校验。
    normalized = dict(data) if isinstance(data, dict) else data
    if isinstance(normalized, dict) and 'answer_id' in normalized:
        from uuid import UUID
        if isinstance(normalized['answer_id'], UUID):
            normalized['answer_id'] = str(normalized['answer_id'])
    serializer = serializer_class(data=normalized)
    try:
        serializer.is_valid(raise_exception=True)
    except ValidationError:
        raise invalid() from None
    return serializer.validated_data


def _fields(row, names):
    """row为本人记录；names明确限制可公开字段。"""
    return {name: getattr(row, name) for name in names}


def _bookmark(row, user):
    """row为本人收藏；实时授权失败时隐藏用户备注。"""
    try:
        access_snapshot(user, row.release_id)
        available = True
    except KnowledgeError:
        available = False
    return {**_fields(row, ('id', 'release_id', 'core_card_id', 'created_at', 'updated_at')),
            'available': available, 'note': row.note if available else None}


def save_bookmark(user, release_id, card_id, data):
    """user为会话用户；release/card来自路由，备注由严格输入验证后覆盖。"""
    data = _validate(SaveBookmarkSerializer, data)
    release_id = _uuid(release_id, not_found)
    if not isinstance(card_id, str) or not 1 <= len(card_id) <= 240:
        raise not_found()
    before = access_snapshot(user, release_id)
    KnowledgeRepository(user).get_card(release_id, card_id)
    with owner_transaction(user.pk):
        current = _current_user(user, lock=True)
        if access_snapshot(current, release_id) != before:
            raise not_found()
        row, _ = Bookmark.objects.get_or_create(owner=current, release_id=release_id, core_card_id=card_id)
        if 'note' in data:
            row.note = data['note']
            row.save(update_fields=['note', 'updated_at'])
        return _bookmark(row, current)


def delete_bookmark(user, release_id, card_id):
    """user为会话用户；失去知识许可仍可删除自己的收藏，重复删除同样成功。"""
    release_id = _uuid(release_id, not_found)
    with owner_transaction(user.pk):
        current = _current_user(user)
        Bookmark.objects.filter(owner=current, release_id=release_id, core_card_id=card_id).delete()


def _page(query, user, kind):
    """query为白名单分页参数；签名绑定用户epoch、筛选与页大小，十五分钟过期。"""
    allowed = {'cursor', 'limit'} | ({'problem_id', 'status'} if kind == 'actions' else set())
    if not isinstance(query, dict) or not set(query) <= allowed:
        raise invalid()
    limit, cursor = query.get('limit', 20), query.get('cursor', '')
    if type(limit) is not int or not 1 <= limit <= 100 or not isinstance(cursor, str) or len(cursor) > 4096:
        raise invalid()
    binding = {'owner': str(user.pk), 'epoch': user.auth_epoch, 'limit': limit,
               'problem_id': str(query.get('problem_id', '')), 'status': query.get('status', '')}
    if kind == 'actions':
        from .models import STATUSES
        if binding['status'] and binding['status'] not in STATUSES:
            raise invalid()
        if binding['problem_id']:
            _uuid(binding['problem_id'], invalid)
    after = None
    if cursor:
        try:
            payload = signing.loads(cursor, salt='personal.' + kind, max_age=900)
            if payload['binding'] != binding:
                raise ValueError('binding')
            date = parse_datetime(payload['updated_at'])
            if date is None or timezone.is_naive(date):
                raise ValueError('date')
            after = (date, _uuid(payload['id'], invalid))
        except (signing.BadSignature, ValueError, KeyError, TypeError):
            raise invalid() from None
    return limit, binding, after


def _after(rows, after):
    """rows为本人有序候选；after为已验签的时间与UUID键。"""
    if after:
        rows = rows.filter(Q(updated_at__lt=after[0]) | Q(updated_at=after[0], id__gt=after[1]))
    return rows.order_by('-updated_at', 'id')


def _cursor(row, binding, kind):
    """row为本页最后一条可见记录，binding绑定当前查询而不泄漏隐藏记录ID。"""
    return signing.dumps({'binding': binding, 'updated_at': row.updated_at.isoformat(), 'id': str(row.pk)},
                         salt='personal.' + kind)


def list_bookmarks(user, query):
    """user为会话用户；本人失效收藏保留无备注占位供删除。"""
    with owner_transaction(user.pk):
        current = _current_user(user)
        limit, binding, after = _page(query, current, 'bookmarks')
        rows = list(_after(Bookmark.objects.filter(owner=current), after)[:limit + 1])
        items = [_bookmark(row, current) for row in rows[:limit]]
        return {'items': items, 'next_cursor': _cursor(rows[limit - 1], binding, 'bookmarks') if len(rows) > limit else None}


def _answer_context(user, answer_id):
    """answer_id为本人正式答案；投影与schema读取在atomic外，记录最终复核需要的许可快照。"""
    payload = get_answer(user, answer_id)
    before = analysis_snapshot(user, payload['release_id'])
    return payload, before


def _recheck(user, payload, before):
    """payload/before来自刚完成的答案读取；在最终事务重查归属、删除状态、发布和完整性。"""
    _get(user, payload['problem_id'])
    if (analysis_snapshot(user, payload['release_id']) != before
            or not Answer.objects.filter(pk=payload['id'], owner=user,
                problem_id=payload['problem_id'], content_hash=payload['content_hash'],
                run__job__status='succeeded', run__outcome='answer').exists()):
        raise not_found()


def _action(row, payload):
    """row为本人行动；四项行动说明从实际答案序号白名单投影。"""
    actions = payload['content']['actions']
    if not 0 <= row.action_index < len(actions):
        raise not_found()
    return {**_fields(row, ('id', 'problem_id', 'answer_id', 'action_index', 'status',
                           'observation', 'revision', 'created_at', 'updated_at')),
            **{name: actions[row.action_index][name] for name in ACTION_FIELDS}}


def create_action(user, data):
    """user为会话用户；data仅答案ID与真实行动序号，重复创建不覆盖观察。"""
    data = _validate(CreateActionSerializer, data)
    payload, before = _answer_context(user, data['answer_id'])
    if data['action_index'] >= len(payload['content']['actions']):
        raise not_found()
    with owner_transaction(user.pk):
        current = _current_user(user, lock=True)
        _recheck(current, payload, before)
        row, _ = ActionRecord.objects.get_or_create(owner=current, answer_id=payload['id'],
            action_index=data['action_index'], defaults={'problem_id': payload['problem_id']})
        return _action(row, payload)


def update_action(user, action_id, data):
    """action_id为本人记录，data为状态/观察及必须匹配的修订号。"""
    data = _validate(UpdateActionSerializer, data)
    action_id = _uuid(action_id, not_found)
    with owner_transaction(user.pk):
        current = _current_user(user)
        row = ActionRecord.objects.filter(owner=current, pk=action_id).first()
        if row is None:
            raise not_found()
    payload, before = _answer_context(user, row.answer_id)
    with owner_transaction(user.pk):
        current = _current_user(user)
        _recheck(current, payload, before)
        row = ActionRecord.objects.select_for_update().filter(owner=current, pk=action_id).first()
        if row is None or str(row.answer_id) != payload['id']:
            raise not_found()
        if row.revision != data['expected_revision']:
            raise ProblemError('REVISION_CONFLICT', '行动已更新，请刷新后重试', 409, row.revision)
        if row.revision == 9223372036854775807:
            raise unavailable()
        fields = [name for name in ('status', 'observation') if name in data]
        for name in fields:
            setattr(row, name, data[name])
        row.revision += 1
        row.save(update_fields=[*fields, 'revision', 'updated_at'])
        return _action(row, payload)


def list_actions(user, query):
    """query为本人行动筛选；按批扫描并投影授权记录，游标不暴露跳过的记录。"""
    with owner_transaction(user.pk):
        current = _current_user(user)
        limit, binding, after = _page(query, current, 'actions')
    visible, contexts = [], {}
    while len(visible) <= limit:
        with owner_transaction(user.pk):
            current = _current_user(user)
            rows = ActionRecord.objects.filter(owner=current, problem__status__in=['active', 'archived'])
            if binding['problem_id']:
                rows = rows.filter(problem_id=binding['problem_id'])
            if binding['status']:
                rows = rows.filter(status=binding['status'])
            batch = list(_after(rows, after)[:100])
        if not batch:
            break
        for row in batch:
            try:
                if row.answer_id not in contexts:
                    contexts[row.answer_id] = _answer_context(user, row.answer_id)
                payload, before = contexts[row.answer_id]
                visible.append((row, _action(row, payload)))
            except (ProblemError, KnowledgeError) as error:
                if error.status != 404:
                    raise
                continue
            if len(visible) > limit:
                break
        after = (batch[-1].updated_at, batch[-1].pk)
    with owner_transaction(user.pk):
        current = _current_user(user)
        for row, _ in visible:
            _recheck(current, *contexts[row.answer_id])
    return {'items': [item for _, item in visible[:limit]],
            'next_cursor': _cursor(visible[limit - 1][0], binding, 'actions') if len(visible) > limit else None}


def create_feedback(user, data):
    """user为会话用户；仅对真实可访问正式答案提交评价，不触发模型。"""
    data = _validate(CreateFeedbackSerializer, data)
    payload, before = _answer_context(user, data['answer_id'])
    with owner_transaction(user.pk):
        current = _current_user(user)
        _recheck(current, payload, before)
        row = Feedback.objects.create(owner=current, answer_id=payload['id'],
                                      category=data['category'], comment=data['comment'])
        return _fields(row, ('id', 'answer_id', 'category', 'comment', 'created_at'))
