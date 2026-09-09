"""仅独立迁移角色可调用的有界个人数据维护；不向runtime增加跨租户DML。"""
import hashlib
import json
import os
import re
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4
from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.contrib.sessions.backends.db import SessionStore
from django.core import signing
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.dateparse import parse_datetime
from .export_worker import file_path


def require_manager(db):
    """db必须为显式本机维护连接，验证其为表owner而非runtime/superuser/BYPASS角色。"""
    row = db.execute('''SELECT current_user, r.rolsuper, r.rolbypassrls,
        pg_get_userbyid(c.relowner) FROM pg_roles r CROSS JOIN pg_class c
        WHERE r.rolname=current_user AND c.oid='public.operations_personalexport'::regclass''').fetchone()
    if row is None or row[0] == settings.SB_RUNTIME_DB_ROLE or row[1] or row[2] or row[0] != row[3]:
        raise ValueError('隐私维护必须使用独立非超级用户迁移连接')


def owner_digest(owner_id):
    """owner_id为已核验UUID；独立删除清单只保存可重放HMAC，不保存邮箱或原UUID。"""
    return salted_hmac('privacy.deleted-owner.v1', str(UUID(str(owner_id))), algorithm='sha256').hexdigest()


def _ledger_path(owner_id, *, create=False):
    """owner_id为维护目标；清单目录必须独立于在线私有数据目录和其备份。"""
    directory = Path(settings.SB_DELETION_LEDGER_ROOT)
    private = Path(settings.SB_PRIVATE_DATA_ROOT).resolve()
    if not directory.is_absolute() or directory.is_symlink() or directory.resolve().is_relative_to(private):
        raise ValueError('删除清单目录必须独立且不可为符号链接')
    if create:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / (owner_digest(owner_id) + '.deletion')
    if path.is_symlink():
        raise ValueError('删除清单不可为符号链接')
    return path


def deletion_record(owner_id, now):
    """owner_id/now用于恢复重放；损坏或签名无效立即停止，不忽略删除清单。"""
    path = _ledger_path(owner_id)
    if not path.exists():
        return None
    record = signing.loads(path.read_text(), salt='privacy.deletion-ledger.v1')
    if record['owner_digest'] != owner_digest(owner_id):
        raise ValueError('删除清单身份不符')
    return record if parse_datetime(record['retain_until']) > now else None


def _record_deletion(owner_id, requested_at, now):
    """owner_id/requested_at/now为实际到期删除；先持久化独立清单再清库，可安全重复。"""
    existing = deletion_record(owner_id, now)
    if existing:
        return existing
    record = {'owner_digest': owner_digest(owner_id), 'requested_at': requested_at.isoformat(),
        'purged_at': now.isoformat(), 'retain_until': (now + timedelta(days=42)).isoformat()}
    path = _ledger_path(owner_id, create=True)
    # 过期记录仅覆盖同一HMAC的确切目标，不批量重写清单。
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(signing.dumps(record, salt='privacy.deletion-ledger.v1'))
        stream.flush()
        os.fsync(stream.fileno())
    return record


def _exports(db, owner_id, now, *, all_files=False):
    """db/owner_id/now为受控目标；仅删除该owner精确导出键及超过24小时的孤立尝试。"""
    rows = db.execute('''SELECT id,file_key FROM operations_personalexport WHERE owner_id=%s
        AND (%s OR expires_at<=%s OR status='expired')''', [owner_id, all_files, now]).fetchall()
    removed = 0
    for identifier, key in rows:
        if key:
            file_path(owner_id, key).unlink(missing_ok=True)
            removed += 1
        db.execute('''UPDATE operations_personalexport SET status='expired',file_key='',binding='{}',
            content_hash='',lease_token=NULL,lease_until=NULL,updated_at=%s WHERE id=%s AND owner_id=%s''', [now, identifier, owner_id])
    directory = Path(settings.SB_PRIVATE_DATA_ROOT).resolve() / 'exports' / str(owner_id)
    if directory.is_symlink():
        raise ValueError('导出目录不可为符号链接')
    if directory.exists():
        checked = 0
        for entry in directory.iterdir():
            checked += 1
            if checked > 10000:
                raise ValueError('导出文件过多，需分批维护')
            if not re.fullmatch(r'[0-9a-f-]{36}-[0-9a-f-]{36}\.json', entry.name):
                continue
            path = file_path(owner_id, entry.name)
            referenced = db.execute('SELECT 1 FROM operations_personalexport WHERE owner_id=%s AND file_key=%s', [owner_id, entry.name]).fetchone()
            if all_files or (not referenced and path.stat().st_mtime <= (now - timedelta(hours=24)).timestamp()):
                path.unlink(missing_ok=True)
                removed += 1
    return removed


def _sessions(db, owner_id):
    """db/owner_id为可信维护连接与目标；有界翻页解码并仅删除该账号的确切session键。"""
    after = ''
    while True:
        rows = db.execute('SELECT session_key,session_data FROM django_session WHERE session_key>%s ORDER BY session_key LIMIT 500', [after]).fetchall()
        if not rows:
            return
        for key, data in rows:
            if SessionStore().decode(data).get('_auth_user_id') == str(owner_id):
                db.execute('DELETE FROM django_session WHERE session_key=%s', [key])
        after = rows[-1][0]


def _password_resets(db, owner_id, now, *, all_files=False):
    """db/owner_id/now限定本次维护目标；只清理到期/终态找回记录及30分钟孤立捕获。"""
    from accounts.password_reset import capture_directory, remove_capture
    rows = db.execute('''SELECT id,delivery FROM accounts_passwordresetdelivery WHERE user_id=%s
        AND (%s OR expires_at<=%s OR status IN ('cancelled','failed','consumed'))''', [owner_id, all_files, now]).fetchall()
    removed = 0
    for identifier, delivery in rows:
        if delivery == 'local_capture':
            path = capture_directory(owner_id) / (str(identifier) + '.json')
            existed = path.exists()
            remove_capture(owner_id, identifier)
            removed += int(existed)
        db.execute('DELETE FROM accounts_passwordresetdelivery WHERE id=%s AND user_id=%s', [identifier, owner_id])
    directory = capture_directory(owner_id)
    if directory.exists():
        for index, entry in enumerate(directory.iterdir()):
            if index >= 10000:
                raise ValueError('捕获文件过多，需分批维护')
            if not re.fullmatch(r'[0-9a-f-]{36}\.json', entry.name):
                continue
            identifier = UUID(entry.stem)
            referenced = db.execute('SELECT 1 FROM accounts_passwordresetdelivery WHERE id=%s AND user_id=%s', [identifier, owner_id]).fetchone()
            if all_files or (not referenced and entry.stat().st_mtime <= (now - timedelta(seconds=1800)).timestamp()):
                remove_capture(owner_id, identifier)
                removed += 1
    return removed


def _invitations(db, email):
    """db/email为到期注销账号；邀请捕获文件仅按固定格式与完整字段/邮箱匹配删除。"""
    db.execute('DELETE FROM accounts_invitation WHERE lower(email)=lower(%s)', [email])
    directory = Path(settings.SB_PRIVATE_DATA_ROOT).resolve()
    if not directory.exists():
        return
    for path in directory.glob('invitation-*.json'):
        if path.is_symlink() or not re.fullmatch(r'invitation-[0-9a-f-]{36}\.json', path.name):
            continue
        if path.stat().st_size > 8192:
            continue
        with path.open() as stream:
            value = json.load(stream)
        if isinstance(value, dict) and set(value) == {'email', 'invite_token', 'expires_at'} and value['email'].lower() == email.lower():
            path.unlink()


def _purge_records(db, owner_id, problem_ids, *, all_personal=False):
    """db/owner_id/problem_ids为严格限定目标；按复合外键反序清除原文和内部快照。"""
    sessions = [row[0] for row in db.execute('SELECT id FROM learning_learningsession WHERE owner_id=%s AND (%s OR problem_id=ANY(%s))',
        [owner_id, all_personal, problem_ids]).fetchall()]
    runs = db.execute('''SELECT id,job_id FROM runs_analysisrun WHERE owner_id=%s
        AND (%s OR problem_id=ANY(%s) OR learning_session_id=ANY(%s))''', [owner_id, all_personal, problem_ids, sessions]).fetchall()
    run_ids, jobs = [row[0] for row in runs], [row[1] for row in runs]
    # 未调用预留释放，有实际调用则结算；防止垃圾桶清理损坏仍有效账号的月度额度。
    reservations = db.execute('''SELECT r.id,r.bucket_id,EXISTS(SELECT 1 FROM operations_usageentry u WHERE u.run_id=r.run_id)
        FROM operations_runreservation r WHERE r.owner_id=%s AND r.run_id=ANY(%s) AND r.state='reserved' FOR UPDATE''', [owner_id, run_ids]).fetchall()
    for identifier, bucket, consumed in reservations:
        db.execute('''UPDATE operations_quotabucket SET reserved_runs=reserved_runs-1,
            settled_runs=settled_runs+%s,revision=revision+1 WHERE id=%s AND owner_id=%s''', [int(consumed), bucket, owner_id])
        db.execute('UPDATE operations_runreservation SET state=%s WHERE id=%s AND owner_id=%s', ['settled' if consumed else 'released', identifier, owner_id])
    db.execute('UPDATE problems_message SET run_id=NULL WHERE owner_id=%s AND run_id=ANY(%s)', [owner_id, run_ids])
    db.execute('DELETE FROM personal_feedback WHERE owner_id=%s AND (%s OR answer_id IN (SELECT id FROM answers_answer WHERE problem_id=ANY(%s)))', [owner_id, all_personal, problem_ids])
    db.execute('DELETE FROM personal_actionrecord WHERE owner_id=%s AND (%s OR problem_id=ANY(%s))', [owner_id, all_personal, problem_ids])
    db.execute('DELETE FROM learning_learningturn WHERE owner_id=%s AND learning_session_id=ANY(%s)', [owner_id, sessions])
    for table in ('operations_usageentry', 'operations_runreservation', 'answers_answer'):
        db.execute(f'DELETE FROM {table} WHERE owner_id=%s AND run_id=ANY(%s)', [owner_id, run_ids])
    db.execute('DELETE FROM runs_jobevent WHERE owner_id=%s AND job_id=ANY(%s)', [owner_id, jobs])
    db.execute('DELETE FROM runs_analysisrun WHERE owner_id=%s AND id=ANY(%s)', [owner_id, run_ids])
    db.execute('DELETE FROM runs_job WHERE owner_id=%s AND (%s OR id=ANY(%s))', [owner_id, all_personal, jobs])
    db.execute('DELETE FROM problems_message WHERE owner_id=%s AND (%s OR problem_id=ANY(%s))', [owner_id, all_personal, problem_ids])
    db.execute('DELETE FROM learning_learningsession WHERE owner_id=%s AND id=ANY(%s)', [owner_id, sessions])
    db.execute('DELETE FROM problems_idempotencyrecord WHERE owner_id=%s AND (%s OR resource_id=ANY(%s))', [owner_id, all_personal, problem_ids + run_ids + sessions])
    db.execute('DELETE FROM problems_problem WHERE owner_id=%s AND id=ANY(%s)', [owner_id, problem_ids])
    if all_personal:
        for table in ('personal_bookmark', 'operations_personalexport', 'operations_quotabucket'):
            db.execute(f'DELETE FROM {table} WHERE owner_id=%s', [owner_id])


def maintain_owner(db, owner_id, *, now=None, replay=False):
    """db为独立迁移连接，owner_id为可信命令UUID；只处理已到期个人记录及可验证删除重放。"""
    require_manager(db)
    owner_id, now = UUID(str(owner_id)), now or timezone.now()
    result = {'account_purged': False, 'problems_purged': 0, 'files_removed': 0}
    with db.transaction():
        user = db.execute('SELECT status,deletion_requested_at,email,is_staff,is_superuser FROM accounts_user WHERE id=%s FOR UPDATE', [owner_id]).fetchone()
        if user is None:
            return result
        status, requested_at, email, staff, superuser = user
        if staff or superuser:
            return result
        record = deletion_record(owner_id, now) if replay else None
        due = status == 'deletion_pending' and requested_at is not None and requested_at + timedelta(days=7) <= now
        if record:
            due, requested_at = True, parse_datetime(record['requested_at'])
        result['files_removed'] = _exports(db, owner_id, now, all_files=due)
        result['files_removed'] += _password_resets(db, owner_id, now, all_files=due)
        problems = [row[0] for row in db.execute('''SELECT id FROM problems_problem WHERE owner_id=%s
            AND (%s OR (status='deleted' AND deleted_at<=%s)) ORDER BY id FOR UPDATE''', [owner_id, due, now - timedelta(days=30)]).fetchall()]
        if due:
            _record_deletion(owner_id, requested_at, now)
            usage = db.execute('''SELECT date_trunc('month',created_at)::date,count(*),
                CASE WHEN count(input_tokens)=count(*) THEN sum(input_tokens) ELSE NULL END,
                CASE WHEN count(output_tokens)=count(*) THEN sum(output_tokens) ELSE NULL END,
                max(created_at)+interval '90 days' FROM operations_usageentry WHERE owner_id=%s
                AND created_at>%s GROUP BY 1''', [owner_id, now - timedelta(days=90)]).fetchall()
            for period, count, inputs, outputs, expiry in usage:
                db.execute('''INSERT INTO operations_retainedusage(id,created_at,updated_at,period,call_count,input_tokens,output_tokens,expires_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''', [uuid4(), now, now, period, count, inputs, outputs, expiry])
            _sessions(db, owner_id)
            _invitations(db, email)
            db.execute('DELETE FROM accounts_policyacceptance WHERE user_id=%s', [owner_id])
            db.execute('DELETE FROM knowledge_librarygrant WHERE owner_id=%s', [owner_id])
            db.execute('''DELETE FROM publishing_adminmutation WHERE operation LIKE %s
                OR response->>'id'=%s OR response->>'owner_id'=%s''',
                ['%%/api/v1/admin/users/' + str(owner_id) + '/%%', str(owner_id), str(owner_id)])
            db.execute('''UPDATE administration_adminaudit SET actor_id=CASE WHEN actor_id=%s THEN %s ELSE actor_id END,
                target_id=NULL,reason='',request_id=NULL WHERE actor_id=%s OR target_id=%s''', [owner_id, UUID(int=0), owner_id, owner_id])
        _purge_records(db, owner_id, problems, all_personal=due)
        result['problems_purged'] = len(problems)
        if due:
            db.execute('''UPDATE accounts_user SET status='disabled', email=%s,display_name='已删除账号',password='!',
                last_login=NULL,email_verified_at=NULL,timezone='UTC',theme='system',auth_epoch=auth_epoch+1,
                access_revision=access_revision+1,deletion_requested_at=NULL,updated_at=%s WHERE id=%s''',
                [f'deleted-{uuid4().hex}@invalid.example', now, owner_id])
            result['account_purged'] = True
        # 与本批直接生命周期一并执行明确已定的7d事件/内部快照、48h终态幂等保留。
        db.execute('DELETE FROM runs_jobevent WHERE owner_id=%s AND created_at<=%s', [owner_id, now - timedelta(days=7)])
        db.execute('''UPDATE runs_analysisrun SET internal_request=NULL,internal_session=NULL,internal_draft=NULL,
            internal_state='{}',authorization_snapshot='{}' WHERE owner_id=%s AND job_id IN
            (SELECT id FROM runs_job WHERE owner_id=%s AND status IN ('succeeded','failed','cancelled') AND finished_at<=%s)''', [owner_id, owner_id, now - timedelta(days=7)])
        db.execute('''DELETE FROM problems_idempotencyrecord i WHERE i.owner_id=%s AND i.expires_at<=%s AND i.status='completed'
            AND NOT EXISTS (SELECT 1 FROM runs_analysisrun r JOIN runs_job j ON j.id=r.job_id
                WHERE r.owner_id=i.owner_id AND r.id=i.resource_id AND j.status IN ('queued','running','cancel_requested'))
            AND NOT EXISTS (SELECT 1 FROM operations_personalexport e WHERE e.owner_id=i.owner_id
                AND e.id=i.resource_id AND e.status IN ('queued','running'))''', [owner_id, now])
    return result


def cancel_deletion(db, owner_id, password, reason, *, now=None):
    """db/owner_id/password/reason来自本机TTY支持命令；七天内复验本人，撤旧grant/session。"""
    require_manager(db)
    owner_id, now = UUID(str(owner_id)), now or timezone.now()
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
        raise ValueError('必须提供有界支持原因')
    with db.transaction():
        row = db.execute('SELECT status,deletion_requested_at,password,is_staff,is_superuser FROM accounts_user WHERE id=%s FOR UPDATE', [owner_id]).fetchone()
        if (row is None or row[0] != 'deletion_pending' or row[1] is None or row[1] + timedelta(days=7) <= now
                or row[3] or row[4] or not check_password(password, row[2]) or deletion_record(owner_id, now)):
            raise ValueError('目标不可恢复或本人核验失败')
        _sessions(db, owner_id)
        db.execute('UPDATE knowledge_librarygrant SET status=\'revoked\',revoked_at=%s,updated_at=%s WHERE owner_id=%s', [now, now, owner_id])
        db.execute('''UPDATE accounts_user SET status='active',deletion_requested_at=NULL,auth_epoch=auth_epoch+1,
            access_revision=access_revision+1,updated_at=%s WHERE id=%s''', [now, owner_id])
        directory = _ledger_path(owner_id, create=True).parent
        record = {'action': 'cancel_deletion', 'owner_digest': owner_digest(owner_id),
            'reason_digest': hashlib.sha256(reason.encode()).hexdigest(), 'occurred_at': now.isoformat()}
        descriptor = os.open(directory / (str(uuid4()) + '.support'), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(signing.dumps(record, salt='privacy.support.v1'))
            stream.flush()
            os.fsync(stream.fileno())
