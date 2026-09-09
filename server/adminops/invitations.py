"""邀请明文仅交付到本机0700私有根下0600捕获文件；公开回执只含编号。"""
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from django.conf import settings
from accounts.models import User, Invitation
from accounts.services import issue_invitation
from administration.bootstrap import private_outfile
from publishing.services import mutate
from .accounts import audit, failure


def invite(request, data):
    """request/data为真实管理员和目标邮箱；重放复用原安全回执，不再次创建邀请或文件。"""
    created_file = None
    def execute(actor):
        """actor为事务内管理员；文件写失败使邀请和幂等记录一起回滚。"""
        nonlocal created_file
        if settings.SB_ENV != 'development':
            raise failure('INVITATION_DELIVERY_UNAVAILABLE', 503)
        email = User.objects.normalize_email(data['email'])
        if User.objects.filter(email__iexact=email).exists():
            raise failure('ACCOUNT_EXISTS')
        token = issue_invitation(email)
        invitation = Invitation.objects.get(token_hash=hashlib.sha256(token.encode()).hexdigest())
        delivery_id = uuid4()
        output = Path(settings.SB_PRIVATE_DATA_ROOT).resolve() / ('invitation-' + str(delivery_id) + '.json')
        try:
            with private_outfile(output) as handle:
                created_file = output
                json.dump({'email': email, 'invite_token': token, 'expires_at': invitation.expires_at.isoformat()}, handle)
                handle.write('\n')
        except (OSError, ValueError):
            raise failure('INVITATION_DELIVERY_UNAVAILABLE', 503) from None
        audit(actor, 'accounts.invite', delivery_id, request)
        return {'delivery': 'local_capture', 'delivery_id': delivery_id, 'expires_at': invitation.expires_at}
    try:
        return mutate(request, 'accounts.invite', data, execute, 201)
    except Exception:
        if created_file is not None:
            created_file.unlink(missing_ok=True)
        raise
