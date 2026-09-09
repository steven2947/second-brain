"""个人记录只保存用户输入与正式知识标识，不复制建议或知识正文。"""
from django.conf import settings
from django.db import models
from django.db.models.functions import Length
from django.db.models.lookups import LessThanOrEqual
from problems.models import Timestamped

STATUSES = ('planned', 'doing', 'done', 'dropped')
CATEGORIES = ('helpful', 'shallow', 'unclear_principle', 'wrong_source', 'other')


class Bookmark(Timestamped):
    """一个用户对固定版本的一张卡最多收藏一次。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    release = models.ForeignKey('knowledge.LibraryRelease', on_delete=models.PROTECT)
    core_card_id = models.CharField(max_length=240)
    note = models.TextField(default='', blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['owner', 'release', 'core_card_id'], name='bookmark_owner_release_card'),
            models.CheckConstraint(condition=LessThanOrEqual(Length('note'), 2000), name='bookmark_note_length'),
        ]
        indexes = [models.Index(fields=['owner', '-updated_at', 'id'], name='bookmark_owner_time')]


class ActionRecord(Timestamped):
    """行动指向已发布答案中的真实序号；观察与完成状态不改变答案。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    problem = models.ForeignKey('problems.Problem', on_delete=models.CASCADE)
    answer = models.ForeignKey('answers.Answer', on_delete=models.CASCADE)
    action_index = models.PositiveIntegerField()
    status = models.CharField(max_length=10, default='planned')
    observation = models.TextField(default='', blank=True)
    revision = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['owner', 'answer', 'action_index'], name='action_owner_answer_index'),
            models.CheckConstraint(condition=models.Q(status__in=STATUSES), name='action_status_valid'),
            models.CheckConstraint(condition=LessThanOrEqual(Length('observation'), 10000), name='action_observation_length'),
        ]
        indexes = [models.Index(fields=['owner', '-updated_at', 'id'], name='action_owner_time')]


class Feedback(Timestamped):
    """对本人真实答案的反馈；审核状态仅由后续管理工作流改变。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    answer = models.ForeignKey('answers.Answer', on_delete=models.CASCADE)
    category = models.CharField(max_length=24)
    comment = models.TextField(default='', blank=True)
    review_status = models.CharField(max_length=10, default='new')

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(category__in=CATEGORIES), name='feedback_category_valid'),
            models.CheckConstraint(condition=models.Q(review_status__in=['new', 'reviewed']), name='feedback_review_valid'),
            models.CheckConstraint(condition=LessThanOrEqual(Length('comment'), 2000), name='feedback_comment_length'),
        ]
