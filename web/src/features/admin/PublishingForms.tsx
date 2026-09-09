/** 人工权利审核与指定用户授权，不以自动校验替代法律事实确认。 */
import { useState } from 'react';
import type { FormEvent } from 'react';
import { grantRelease, listManagedUsers, revokeGrant, saveRights } from '../../api/publishing';
import type { ManagedUser, ReleaseDetail, RightsInput } from '../../api/publishing';
import { PublishingError, usePublishingWrite } from './publishing-shared';

type Draft = { key: string; whole: boolean; scope: string[]; description: string; basis: RightsInput['basis_type']; license: string; proof: string; uses: RightsInput['allowed_uses']; maxChars: number; validUntil: string; status: '' | RightsInput['status'] };
/** 无参数；用途和批准状态不预先替管理员选择。 */
function emptyDraft(): Draft { return { key: crypto.randomUUID(), whole: true, scope: [], description: '', basis: 'permission', license: '', proof: '', uses: [], maxChars: 100, validUntil: '', status: '' }; }
/** draft是已填写人工记录，时间转换为绝对ISO；不含客户端自报审核人。 */
function input(draft: Draft): RightsInput { return { scope_book_ids: draft.whole ? [] : draft.scope, source_description: draft.description, basis_type: draft.basis, license_name: draft.license || null, proof_storage_key: draft.proof || null, allowed_audience: 'granted_users', allowed_uses: draft.uses, quote_policy: draft.uses.includes('quote') ? { max_chars: draft.maxChars } : {}, valid_until: draft.validUntil ? new Date(draft.validUntil).toISOString() : null, status: draft.status as RightsInput['status'] }; }
/** release为当前待审版本，onSaved重新读取持久审核结果而非乐观标绿。 */
export function RightsEditor({ release, onSaved }: { release: ReleaseDetail; onSaved: () => void }) {
  const [rows, setRows] = useState<Draft[]>(() => [emptyDraft()]), [ack, setAck] = useState(false), [validation, setValidation] = useState(''), write = usePublishingWrite();
  /** key定位当前草稿行，patch只更新明确改动，不触碰其他行。 */
  function update(key: string, patch: Partial<Draft>) { setRows(values => values.map(value => value.key === key ? { ...value, ...patch } : value)); }
  /** event为完整记录集的人工提交，缺范围/用途/审核决定时不请求。 */
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!ack || rows.some(row => !row.status || !row.description.trim() || (!row.whole && !row.scope.length) || !row.uses.length)) { setValidation('每条记录都需要来源说明、适用书籍、至少一项待审核用途和明确审核决定。'); return; }
    setValidation('');
    const records = rows.map(input);
    write.submit(`rights:${release.id}`, records, (key, signal) => saveRights(release.id, records, key, signal), () => { setAck(false); setRows([emptyDraft()]); onSaved(); });
  }
  if (release.status === 'published') return <p className="admin-note">已发布版本不可直接改写权利记录。需先撤销发布，再重新审核。</p>;
  return <details className="publishing-editor"><summary>填写 / 重审本版本权利记录</summary><p>填写完整记录集；提交将按后端规则更新本版本审核。技术通过不代表拥有传播、分析或引用许可。证明只填本机已保存的相对存储键，不上传原文。</p>
    {release.rights_records.length > 0 && <p className="admin-note">已有 {release.rights_records.length} 条记录。此表不会自动复制私有证明，请完整核对所有书籍范围，避免漏掉原有许可。</p>}
    <form className="admin-form" onSubmit={submit}>{rows.map((row, index) => <fieldset className="rights-record" key={row.key} disabled={write.disabled}><legend>权利记录 {index + 1}</legend>
      <label>来源与依据说明<textarea value={row.description} maxLength={2000} required onChange={event => update(row.key, { description: event.target.value })} /></label>
      <label>权利依据<select value={row.basis} onChange={event => update(row.key, { basis: event.target.value as Draft['basis'] })}><option value="permission">权利人明确授权</option><option value="license">许可证</option><option value="self_authored">自编内容</option><option value="public_domain">已核实的公有领域</option><option value="other">其他可证明依据</option></select></label>
      <div className="publishing-two"><label>许可证名称（如适用）<input value={row.license} maxLength={500} onChange={event => update(row.key, { license: event.target.value })} /></label><label>证明存储键<input value={row.proof} maxLength={240} required={['permission', 'license', 'other'].includes(row.basis)} placeholder="rights/已登记证明文件" onChange={event => update(row.key, { proof: event.target.value })} /></label></div>
      <label className="check-label"><input type="checkbox" checked={row.whole} onChange={event => update(row.key, { whole: event.target.checked })} />覆盖本版本全部 {release.books.length} 本书</label>
      {!row.whole && <div className="rights-choices" role="group" aria-label={`记录${index + 1}适用书籍`}>{release.books.map(book => <label className="check-label" key={book.id}><input type="checkbox" checked={row.scope.includes(book.id)} onChange={event => update(row.key, { scope: event.target.checked ? [...row.scope, book.id] : row.scope.filter(id => id !== book.id) })} />{book.title} · {book.author_display ?? '作者未知'}</label>)}</div>}
      <div className="rights-choices" role="group" aria-label={`记录${index + 1}允许用途`}>{(['browse', 'analyze', 'quote'] as const).map(use => <label className="check-label" key={use}><input type="checkbox" checked={row.uses.includes(use)} onChange={event => update(row.key, { uses: event.target.checked ? [...row.uses, use] : row.uses.filter(value => value !== use) })} />{use === 'browse' ? '知识浏览' : use === 'analyze' ? '用于分析与学习' : '原文短引'}</label>)}</div>
      {row.uses.includes('quote') && <label>单段引用字符上限<input type="number" min={1} max={2000} value={row.maxChars} required onChange={event => update(row.key, { maxChars: Number(event.target.value) })} /><small>技术限额不是法律安全保证，应以实际许可范围为准。</small></label>}
      <div className="publishing-two"><label>权利有效期至（本地时间，可留空）<input type="datetime-local" value={row.validUntil} onChange={event => update(row.key, { validUntil: event.target.value })} /></label><label>人工审核决定<select value={row.status} required onChange={event => update(row.key, { status: event.target.value as Draft['status'] })}><option value="">请明确选择</option><option value="approved">批准此记录</option><option value="rejected">拒绝此记录</option></select></label></div>
      {rows.length > 1 && <button className="secondary-action" type="button" onClick={() => setRows(values => values.filter(value => value.key !== row.key))}>移除这条未提交记录</button>}
    </fieldset>)}<button type="button" className="secondary-action" disabled={write.disabled || rows.length >= 20} onClick={() => setRows(values => [...values, emptyDraft()])}>增加另一份权利记录</button>
      <label className="check-label"><input type="checkbox" checked={ack} onChange={event => setAck(event.target.checked)} />我已核对完整记录集、适用书籍、期限和用途，并承担人工审核决定</label>{validation && <p role="alert">{validation}</p>}<PublishingError failure={write.failure} /><button type="submit" disabled={write.disabled || !ack}>{write.pending ? '正在保存…' : '保存人工审核记录'}</button>
    </form></details>;
}
/** release为选中固定版本；账号列表仅在具备accounts.view且主动点击时读取。 */
export function GrantEditor({ release, canListUsers, onSaved }: { release: ReleaseDetail; canListUsers: boolean; onSaved: () => void }) {
  const write = usePublishingWrite(), lookup = usePublishingWrite();
  const [owner, setOwner] = useState(''), [expires, setExpires] = useState(''), [reason, setReason] = useState(''), [ack, setAck] = useState(false), [notice, setNotice] = useState('');
  const [users, setUsers] = useState<ManagedUser[]>([]), [cursor, setCursor] = useState<string | null>(null);
  const validOwner = /^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(owner);
  /** event明确给普通用户授予当前版本，不授予管理权限。 */
  function grant(event: FormEvent) { event.preventDefault(); if (!validOwner || !ack) return; const until = expires ? new Date(expires).toISOString() : null; write.submit(`grant:${owner}:${release.id}`, { expires_at: until }, (key, signal) => grantRelease(owner, release.id, until, key, signal), () => { setNotice('已保存该用户的版本授权。'); setAck(false); onSaved(); }); }
  /** event明确撤销指定用户的版本授权，不删除用户的原始问题。 */
  function revoke(event: FormEvent) { event.preventDefault(); if (!validOwner || !reason.trim() || !ack) return; write.submit(`ungrant:${owner}:${release.id}`, { reason }, (key, signal) => revokeGrant(owner, release.id, reason, key, signal), () => { setNotice('已撤销该用户的版本授权。'); setReason(''); setAck(false); onSaved(); }); }
  /** next只取服务端返回游标，查询由用户点击触发，不自动枚举用户。 */
  function findUsers(next: string | null = null) { void lookup.run(signal => listManagedUsers(next, signal), result => { setUsers(result.items); setCursor(result.next_cursor); }); }
  return <section className="publishing-actions"><h4>4. 指定用户授权</h4><p>只给指定普通账号授予整个版本的阅读权，分析和引用仍受本版本权利记录约束。</p>
    {canListUsers && <><button className="secondary-action" type="button" disabled={lookup.disabled} onClick={() => findUsers()}>查找可授权账号</button>{users.length > 0 && <ul className="managed-users">{users.map(user => <li key={user.id}><button type="button" disabled={user.status !== 'active'} onClick={() => { setOwner(user.id); setAck(false); setNotice(''); }}>{user.display_name} · {user.email} · {user.status === 'active' ? '正常' : '不可授权'}</button></li>)}</ul>}{cursor && <button type="button" disabled={lookup.disabled} onClick={() => findUsers(cursor)}>下一批账号</button>}<PublishingError failure={lookup.failure} /></>}
    <label className="grant-target">目标普通账号 ID<input value={owner} onChange={event => { setOwner(event.target.value.trim()); setAck(false); setNotice(''); }} placeholder="完整账号UUID" maxLength={36} /></label>
    <label className="check-label"><input type="checkbox" checked={ack} onChange={event => setAck(event.target.checked)} />已核对目标账号与版本《{release.title}》，确认执行下方所选动作</label>
    <form className="publishing-inline" onSubmit={grant}><label>授权有效期至（本地时间，可留空）<input type="datetime-local" value={expires} onChange={event => setExpires(event.target.value)} /></label><button type="submit" disabled={write.disabled || !validOwner || !ack || release.status !== 'published'}>授予 / 更新版本授权</button></form>
    <form className="publishing-inline" onSubmit={revoke}><label>撤销授权的原因<input value={reason} maxLength={500} required onChange={event => setReason(event.target.value)} /></label><button type="submit" className="secondary-action" disabled={write.disabled || !validOwner || !ack || !reason.trim()}>撤销该用户授权</button></form><PublishingError failure={write.failure} />{notice && <p role="status">{notice}</p>}
  </section>;
}
