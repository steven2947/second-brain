/** 普通账号运营与次数额度；权限只控制界面，后端对每次操作再次校验。 */
import { useCallback, useState } from 'react';
import type { FormEvent } from 'react';
import type { AdminIdentity } from '../../api/admin';
import { changeAccountStatus, readQuota, saveQuota } from '../../api/adminops';
import type { Quota } from '../../api/adminops';
import { listManagedUsers } from '../../api/publishing';
import type { ManagedUser } from '../../api/publishing';
import { PublishingError, usePublishingRead, usePublishingWrite } from './publishing-shared';

const statusLabels = { active: '可用', disabled: '已停用', deletion_pending: '等待删除' } as const;
type Target = { id: string; status?: ManagedUser['status']; display_name?: string };
/** permissions来自当前管理身份；账号目录只在明确查询后请求。 */
export function AccountOperations({ permissions }: { permissions: AdminIdentity['granted_permissions'] }) {
  const [lookup, setLookup] = useState(false), [target, setTarget] = useState<Target | null>(null), [input, setInput] = useState('');
  const canEdit = permissions.includes('accounts.disable') || permissions.includes('quota.manage');
  /** event是人工选择，UUID格式先在页面校验；不据此宣称目标存在或可操作。 */
  function choose(event: FormEvent) { event.preventDefault(); if (/^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(input.trim())) setTarget({ id: input.trim().toLowerCase() }); }
  return <section className="publishing-section"><h3>普通账号</h3><p>停用会使原会话失效；恢复后仍需重新登录，不增加知识访问权限。</p>
    {permissions.includes('accounts.view') && <><button className="secondary-action" type="button" onClick={() => setLookup(value => !value)}>{lookup ? '收起账号列表' : '查询普通账号'}</button>{lookup && <AccountDirectory onSelect={setTarget} />}</>}
    {canEdit && <form className="publishing-inline" onSubmit={choose}><label>目标普通账号 ID<input value={input} onChange={event => setInput(event.target.value)} maxLength={36} pattern="[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}" required /></label><button type="submit" className="secondary-action">选择此账号</button></form>}
    {target && canEdit && <section className="operations-target" key={`${target.id}:${target.status ?? 'manual'}`}><h4>{target.display_name ?? '已指定目标账号'}</h4><p><code>{target.id}</code>{target.status && ` · ${statusLabels[target.status]}`}</p>
      {target.status === 'deletion_pending' ? <p>账号正在删除流程中，不能从此处恢复或修改额度。</p> : <>{permissions.includes('accounts.disable') && <StatusEditor target={target} onSaved={setTarget} />}{permissions.includes('quota.manage') && <QuotaPanel owner={target.id} />}</>}
    </section>}
  </section>;
}
/** onSelect明确选取当前页账号；列表没有问题、密码或权限明细。 */
function AccountDirectory({ onSelect }: { onSelect: (user: ManagedUser) => void }) {
  const [cursor, setCursor] = useState<string | null>(null), [revision, setRevision] = useState(0);
  const result = usePublishingRead(useCallback((signal: AbortSignal) => listManagedUsers(cursor, signal), [cursor]), revision);
  return <div className="operations-directory"><PublishingError failure={result.failure} />{!result.data && !result.failure && <p role="status">正在读取普通账号…</p>}{result.data?.items.length === 0 && <p>暂无普通账号。</p>}<ul className="managed-users">{result.data?.items.map(user => <li key={user.id}><button type="button" onClick={() => onSelect(user)}><strong>{user.display_name}</strong> · {user.email} · {statusLabels[user.status]}</button></li>)}</ul><div className="publishing-pagination"><button type="button" className="secondary-action" onClick={() => { setCursor(null); setRevision(value => value + 1); }}>刷新账号列表</button>{result.data?.next_cursor && <button type="button" className="secondary-action" onClick={() => setCursor(result.data!.next_cursor)}>下一批账号</button>}</div></div>;
}
/** target为已选普通账号或手工UUID；onSaved仅接受服务端确认的状态。 */
function StatusEditor({ target, onSaved }: { target: Target; onSaved: (user: ManagedUser) => void }) {
  const [expected, setExpected] = useState<'active' | 'disabled'>(target.status === 'disabled' ? 'disabled' : 'active'), [reason, setReason] = useState(''), [confirmed, setConfirmed] = useState(false), write = usePublishingWrite();
  const next = expected === 'active' ? 'disabled' : 'active';
  /** event请求CAS变更，必须确认目标、当前状态和原因；不自动重新解释冲突。 */
  function submit(event: FormEvent) { event.preventDefault(); if (!confirmed || !reason.trim()) return; write.submit(`account:${target.id}`, { expected, next, reason }, (key, signal) => changeAccountStatus(target.id, next, expected, reason, key, signal), onSaved); }
  return <form className="admin-form" onSubmit={submit}>{target.status === 'disabled' && <p role="status">账号已停用，原会话已失效。</p>}{!target.status && <label>你核实的当前状态<select value={expected} onChange={event => { setExpected(event.target.value as 'active' | 'disabled'); setConfirmed(false); }} disabled={write.disabled}><option value="active">可用</option><option value="disabled">已停用</option></select></label>}
    <label>状态变更原因<input value={reason} onChange={event => setReason(event.target.value)} maxLength={500} required disabled={write.disabled} /></label><label className="check-label"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} disabled={write.disabled} />确认变更此普通账号，不涉及管理身份或知识授权</label><PublishingError failure={write.failure} /><button type="submit" disabled={write.disabled || !confirmed || !reason.trim()}>{next === 'disabled' ? '停用账号' : '恢复账号（需重新登录）'}</button>
  </form>;
}
/** owner为目标UUID；额度只在明确读取后加载，避免手输每个字符都请求。 */
function QuotaPanel({ owner }: { owner: string }) {
  const [opened, setOpened] = useState(false), [revision, setRevision] = useState(0), [notice, setNotice] = useState('');
  return <section className="operations-quota"><h4>月度次数额度</h4><p>按 UTC 月份计数。这里控制调用轮数，不代表 token 上限或金额预算。</p><button className="secondary-action" type="button" onClick={() => { setOpened(true); setRevision(value => value + 1); }}>{opened ? '重新读取本月额度' : '读取本月额度'}</button>{notice && <p role="status">{notice}</p>}{opened && <QuotaRead owner={owner} refresh={revision} onSaved={() => { setNotice('本月次数额度已保存。'); setRevision(value => value + 1); }} />}</section>;
}
/** owner/refresh限定额度请求；onSaved刷新当前事实而非在前端自行扣减。 */
function QuotaRead({ owner, refresh, onSaved }: { owner: string; refresh: number; onSaved: () => void }) {
  const result = usePublishingRead(useCallback((signal: AbortSignal) => readQuota(owner, signal), [owner]), refresh);
  return <><PublishingError failure={result.failure} />{!result.data && !result.failure && <p role="status">正在读取额度…</p>}{result.data && <QuotaEditor key={`${result.data.period}:${result.data.revision}`} data={result.data} onSaved={onSaved} />}</>;
}
/** data为服务端当前月事实，onSaved在成功响应后更新显示；不允许压低已占用次数。 */
function QuotaEditor({ data, onSaved }: { data: Quota; onSaved: () => void }) {
  const [limit, setLimit] = useState(String(data.limit_runs)), write = usePublishingWrite(), used = data.reserved_runs + data.settled_runs;
  const valid = /^\d+$/.test(limit) && Number.isSafeInteger(Number(limit)) && Number(limit) >= used;
  /** event以实际修订号保存，竞争失败后保持输入供用户核对。 */
  function submit(event: FormEvent) { event.preventDefault(); if (valid) write.submit(`quota:${data.owner_id}`, { limit, revision: data.revision, period: data.period }, (key, signal) => saveQuota(data.owner_id, Number(limit), data.revision, data.period, key, signal), onSaved); }
  return <form className="admin-form" onSubmit={submit}><p>{data.period.slice(0, 7)} · UTC 月份</p><p>已结算 {data.settled_runs} 次 · 执行中预留 {data.reserved_runs} 次</p><label>本月总次数上限<input type="number" min={used} max={Number.MAX_SAFE_INTEGER} step="1" value={limit} onChange={event => setLimit(event.target.value)} required disabled={write.disabled} /></label><p className="field-help">不能低于已结算与预留合计 {used} 次。其他任务可能同时更新额度，冲突时请重新读取。</p><PublishingError failure={write.failure} /><button type="submit" disabled={write.disabled || !valid}>保存本月额度</button></form>;
}
