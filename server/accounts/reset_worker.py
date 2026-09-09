"""找回密码专用有界发送worker；持久租约、fencing和身份复验，不提供任意发送API。"""
from datetime import timedelta
from smtplib import SMTPException
from uuid import uuid4

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from .models import PasswordResetDelivery, User
from .password_reset import ResetTokenGenerator, configured_channel, eligible, identity_binding, remove_capture, write_capture


def claim(user_id):
    """user_id为受控worker枚举的账号UUID；只领取一条任务，旧租约可在重启后回收。"""
    now = timezone.now()
    with transaction.atomic():
        row = PasswordResetDelivery.objects.select_for_update(skip_locked=True).filter(user_id=user_id).filter(
            Q(status='queued', available_at__lte=now) | Q(status='running', lease_until__lte=now)).order_by('created_at', 'id').first()
        if row is None:
            return None
        if row.expires_at <= now or row.attempts >= 3:
            row.status, row.binding, row.lease_token, row.lease_until = 'failed', '', None, None
            row.save(update_fields=['status', 'binding', 'lease_token', 'lease_until'])
            if row.delivery == 'local_capture':
                remove_capture(row.user_id, row.pk)
            return (row.pk, None)
        row.status, row.lease_token = 'running', uuid4()
        row.lease_until, row.attempts = now + timedelta(seconds=30), row.attempts + 1
        row.save(update_fields=['status', 'lease_token', 'lease_until', 'attempts'])
        return (row.pk, row.lease_token)


def deliver(user_id, identifier, lease_token):
    """user_id/identifier/lease_token均来自已领取任务；发送前锁身份和任务，过时worker无权发送。"""
    if lease_token is None:
        return
    with transaction.atomic():
        # NO KEY UPDATE仍串行化停用/改密，但允许新申请的外键KEY SHARE，避免SMTP延迟泄露账号存在性。
        user = User.objects.select_for_update(no_key=True).filter(pk=user_id).first()
        row = PasswordResetDelivery.objects.select_for_update().filter(pk=identifier, user_id=user_id).first()
        now = timezone.now()
        if row is None or row.status != 'running' or row.lease_token != lease_token or row.lease_until <= now:
            return
        if (not eligible(user) or row.expires_at <= now
                or not constant_time_compare(row.binding, identity_binding(user))):
            row.status, row.binding = 'cancelled', ''
        else:
            token = row.pk.hex + '.' + ResetTokenGenerator(row.pk).make_token(user)
            link = settings.SB_PUBLIC_ORIGIN + '/reset-password#token=' + token
            subject = '第二大脑：重置密码'
            body = f'你申请了重置第二大脑密码。请在申请后30分钟内打开以下链接：\n\n{link}\n\n如果不是你发起的申请，请忽略此邮件。'
            try:
                if configured_channel() != row.delivery:
                    raise ValueError('channel unavailable')
                if row.delivery == 'local_capture':
                    write_capture(row, user.email, subject, body)
                else:
                    with get_connection(backend='django.core.mail.backends.smtp.EmailBackend',
                            host=settings.EMAIL_HOST, port=settings.EMAIL_PORT,
                            username=settings.EMAIL_HOST_USER, password=settings.EMAIL_HOST_PASSWORD,
                            use_tls=settings.EMAIL_USE_TLS, use_ssl=settings.EMAIL_USE_SSL,
                            timeout=settings.EMAIL_TIMEOUT, fail_silently=False) as connection:
                        message = EmailMessage(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], connection=connection)
                        if message.send(fail_silently=False) != 1:
                            raise ValueError('delivery failed')
                row.status = 'sent'
            except (OSError, SMTPException, ValueError):
                row.status = 'failed' if row.attempts >= 3 else 'queued'
                row.available_at = timezone.now() + timedelta(seconds=30 * row.attempts)
                if row.status == 'failed':
                    row.binding = ''
        row.lease_token, row.lease_until = None, None
        row.save(update_fields=['status', 'binding', 'available_at', 'lease_token', 'lease_until'])
        if row.delivery == 'local_capture' and row.status != 'sent':
            remove_capture(row.user_id, row.pk)


def process_one(user_id):
    """user_id为现有worker的受控枚举目标；返回是否处理了一个任务，不输出邮件内容。"""
    lease = claim(user_id)
    if lease is None:
        return False
    deliver(user_id, *lease)
    return True
