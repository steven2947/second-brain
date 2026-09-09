"""知识HTTP输入与公开响应事实源；不序列化ORM或旧核心的完整内部记录。"""
from rest_framework import serializers
from accounts.serializers import StrictSerializer


class PageQuerySerializer(StrictSerializer):
    """只允许有界分页与签名游标。"""
    limit = serializers.IntegerField(min_value=1, max_value=100, required=False, default=20)
    cursor = serializers.CharField(max_length=4096, allow_blank=True, required=False, default='')


class BookQuerySerializer(PageQuerySerializer):
    """书名与作者过滤在获准书目中执行。"""
    q = serializers.CharField(max_length=500, allow_blank=True, required=False, default='')
    author = serializers.CharField(max_length=240, allow_blank=True, required=False, default='')


class CardQuerySerializer(BookQuerySerializer):
    """只在获准固定版本内检索卡片。"""
    book = serializers.CharField(max_length=240, allow_blank=True, required=False, default='')
    type = serializers.CharField(max_length=40, allow_blank=True, required=False, default='')


class DetailQuerySerializer(StrictSerializer):
    """详情无扩展参数，不开放路径、上下文窗口或任意owner字段。"""


class BookSerializer(StrictSerializer):
    """作者未知保持null，不由接口猜测。"""
    id = serializers.CharField()
    title = serializers.CharField()
    author_display = serializers.CharField(allow_null=True)
    metadata_status = serializers.ChoiceField(choices=['verified', 'partial'])


class BookDetailSerializer(BookSerializer):
    """可浏览章节来自当前证据覆盖，gaps描述实际缺口。"""
    release_id = serializers.UUIDField()
    content_version = serializers.CharField(min_length=24, max_length=24)
    chapters = serializers.ListField(child=serializers.CharField())
    gaps = serializers.ListField(child=serializers.CharField())


class LocationSerializer(StrictSerializer):
    """字符定位不伪造原书页码，也不公开磁盘路径。"""
    kind = serializers.ChoiceField(choices=['original', 'evidence_compilation'])
    start = serializers.IntegerField(min_value=0)
    end = serializers.IntegerField(min_value=1)
    paragraph_id = serializers.CharField(allow_null=True)
    notice = serializers.CharField()


class SourcePreviewSerializer(StrictSerializer):
    """仅返回获准的连续原文短引及真实位置。"""
    release_id = serializers.UUIDField()
    evidence_id = serializers.CharField()
    book = BookSerializer()
    chapter = serializers.CharField()
    text = serializers.CharField(max_length=2000)
    truncated = serializers.BooleanField()
    location = LocationSerializer()


class RelationSerializer(StrictSerializer):
    """不嵌套原卡；来源关系与系统推断保留区分。"""
    id = serializers.CharField()
    from_id = serializers.CharField(source='from')
    to_id = serializers.CharField(source='to')
    type = serializers.CharField()
    basis = serializers.ChoiceField(choices=['source', 'inference'])
    rationale = serializers.CharField()


class CardSummarySerializer(StrictSerializer):
    """搜索列表不含内部分数、文件路径或未请求原文。"""
    release_id = serializers.UUIDField()
    card_id = serializers.CharField()
    book = BookSerializer()
    type = serializers.CharField()
    title = serializers.CharField()
    statement = serializers.CharField()


class BrowseCardSerializer(CardSummarySerializer):
    """原理方法不人为缩短，原文预览由独立quote权限决定。"""
    explanation = serializers.CharField(allow_blank=True)
    conditions = serializers.ListField(child=serializers.CharField(allow_blank=True))
    boundaries = serializers.ListField(child=serializers.CharField(allow_blank=True))
    steps = serializers.ListField(child=serializers.CharField(allow_blank=True))
    application_notes = serializers.CharField(allow_blank=True)
    source_claim_type = serializers.ChoiceField(choices=['author_claim', 'quoted_other', 'system_inference', 'unknown'])
    related = RelationSerializer(many=True)
    source_previews = SourcePreviewSerializer(many=True)
    usage_notice = serializers.CharField()
    gaps = serializers.ListField(child=serializers.CharField())


class ReleaseSerializer(StrictSerializer):
    """只列出获准知识版本的公开书目概况。"""
    id = serializers.UUIDField()
    library_id = serializers.UUIDField()
    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    content_version = serializers.CharField(min_length=24, max_length=24)
    book_count = serializers.IntegerField(min_value=1)
    card_count = serializers.IntegerField(min_value=1)


class LibraryPageSerializer(StrictSerializer):
    """获准知识集的分页列表，无全库未授权总数。"""
    items = ReleaseSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class BookPageSerializer(StrictSerializer):
    """版本内书目分页。"""
    release_id = serializers.UUIDField()
    content_version = serializers.CharField(min_length=24, max_length=24)
    items = BookSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class CardPageSerializer(BookPageSerializer):
    """版本内知识卡摘要分页。"""
    items = CardSummarySerializer(many=True)
