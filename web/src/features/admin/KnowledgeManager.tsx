/** 知识管理使用真实登记、持久任务和版本状态；导入、审核、发布保持独立。 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { AdminIdentity } from '../../api/admin';
import { ApiFailure } from '../../api/client';
import { importSource, listImports, listManagedReleases, listSources, publishRelease, readManagedRelease, revokeRelease } from '../../api/publishing';
import type { ManagedRelease } from '../../api/publishing';
import { PublishingError, PublishingFailure, usePublishingRead, usePublishingWrite } from './publishing-shared';
import { GrantEditor, RightsEditor } from './PublishingForms';
import '../../styles/publishing.css';

export const releaseLabels = { staged: '待校验', validated: '技术通过', published: '已发布', revoked: '已撤销' } as const;
export const rightsLabels = { unreviewed: '待审核', approved: '权利通过', rejected: '未通过', expired: '已过期' } as const;
/** identity是刚校验的管理会话，onFailure将失效身份交回上层统一清除。 */
export function KnowledgeManager({ identity, onFailure }: { identity: AdminIdentity; onFailure: (error: ApiFailure) => void }) {
  const permissions = identity.granted_permissions, [revision, setRevision] = useState(0), [selected, setSelected] = useState<string | null>(null);
  const refresh = useCallback(() => setRevision(value => value + 1), []);
  const reject = useCallback((error: ApiFailure) => { if (error.status === 401 || error.code === 'ADMIN_PERMISSION_DENIED') onFailure(error); }, [onFailure]);
  const available = permissions.some(value => value.startsWith('knowledge.') || value === 'grants.manage');
  if (!available) return <section className="admin-panel"><h2>知识管理</h2><p>此账号尚未获得知识管理或授权权限。</p></section>;
  return <PublishingFailure.Provider value={reject}><section className="publishing-main"><header className="publishing-header"><div><p className="section-label">知识管理</p><h2>让知识有序进入书房。</h2><p>登记来源 → 技术校验 → 权利审核 → 发布 → 授权。每一步都保留独立状态。</p></div><button type="button" className="secondary-action" onClick={refresh}>刷新管理记录</button></header>
    {permissions.includes('knowledge.import') && <ImportPanel refresh={revision} onImported={refresh} onSelect={setSelected} />}
    <ReleaseCatalog refresh={revision} onSelect={setSelected} selected={selected} />
    {selected && <ReleasePanel key={selected} id={selected} refresh={revision} permissions={permissions} onSaved={refresh} onClose={() => setSelected(null)} />}
  </section></PublishingFailure.Provider>;
}
/** refresh使登记与导入记录重新读取；onImported更新版本列表，onSelect打开已完成结果。 */
function ImportPanel({ refresh, onImported, onSelect }: { refresh: number; onImported: () => void; onSelect: (id: string) => void }) {
  const [selected, setSelected] = useState(''), [tick, setTick] = useState(0), [cursor, setCursor] = useState<string | null>(null), write = usePublishingWrite();
  const sources = usePublishingRead(useCallback((signal: AbortSignal) => listSources(signal), []), refresh);
  const imports = usePublishingRead(useCallback((signal: AbortSignal) => listImports(cursor, signal), [cursor]), refresh + tick);
  const running = imports.data?.items.some(item => item.status === 'queued' || item.status === 'running');
  const observed = useRef(new Set<string>());
  useEffect(() => { if (!running) return; const timer = window.setTimeout(() => setTick(value => value + 1), 2500); return () => window.clearTimeout(timer); }, [running, imports.data]);
  useEffect(() => { let changed = false; for (const item of imports.data?.items ?? []) if (item.status === 'succeeded' && !observed.current.has(item.id)) { observed.current.add(item.id); changed = true; } if (changed) onImported(); }, [imports.data, onImported]);
  /** event明确请求导入，不自动发布或授权，也不把输入当磁盘路径。 */
  function submit(event: FormEvent) { event.preventDefault(); if (!sources.data?.some(source => source.staging_key === selected)) return; write.submit('import', { selected }, (key, signal) => importSource(selected, key, signal), () => { setCursor(null); onImported(); }); }
  return <section className="publishing-section"><h3>1. 导入已登记来源</h3><p>这里仅显示部署负责人已在本机登记的固定版本。不会上传原书或接受任意网页地址。</p>
    <form className="publishing-inline" onSubmit={submit}><label>选择来源<select value={selected} onChange={event => setSelected(event.target.value)} disabled={write.disabled || !sources.data} required><option value="">请选择已登记来源</option>{sources.data?.map(source => <option key={source.staging_key} value={source.staging_key}>{source.title} · {source.book_count} 本 / {source.card_count} 张卡</option>)}</select></label><button type="submit" disabled={write.disabled || !selected}>{write.pending ? '正在提交…' : '开始技术导入'}</button></form>
    {sources.data?.length === 0 && <p role="status">暂无登记来源。请由部署负责人先执行本机登记，再刷新本页。</p>}<PublishingError failure={sources.failure ?? write.failure ?? imports.failure} />
    <h4>本账号的导入记录</h4>{!imports.data && !imports.failure && <p role="status">正在读取导入记录…</p>}{imports.data?.items.length === 0 && <p>还没有导入任务。</p>}
    <ul className="import-list">{imports.data?.items.map(job => <li key={job.id}><span>{job.status === 'queued' ? '已排队' : job.status === 'running' ? '正在校验固定版本' : job.status === 'succeeded' ? '导入完成，仍需权利审核' : '导入未完成，请核对登记源和当前权限'}</span><code>{job.id.slice(0, 8)}</code>{job.release_id && <button className="secondary-action" type="button" onClick={() => onSelect(job.release_id!)}>查看导入版本</button>}</li>)}</ul>
    <div className="publishing-pagination">{cursor && <button type="button" onClick={() => setCursor(null)}>最新记录</button>}{imports.data?.next_cursor && <button type="button" onClick={() => setCursor(imports.data!.next_cursor)}>较早导入记录</button>}</div>
  </section>;
}
/** refresh重读当前页；selected只控制展开状态，不作为访问授权。 */
function ReleaseCatalog({ refresh, onSelect, selected }: { refresh: number; onSelect: (id: string) => void; selected: string | null }) {
  const [cursor, setCursor] = useState<string | null>(null);
  const result = usePublishingRead(useCallback((signal: AbortSignal) => listManagedReleases(cursor, signal), [cursor]), refresh);
  return <section className="publishing-section"><h3>2. 固定知识版本</h3><PublishingError failure={result.failure} />{!result.data && !result.failure && <p role="status">正在读取版本…</p>}{result.data?.items.length === 0 && <p>当前没有可管理的知识版本。</p>}
    <ul className="release-list">{result.data?.items.map(release => <li key={release.id}><button type="button" aria-expanded={selected === release.id} className="release-select" onClick={() => onSelect(release.id)}><span><strong>{release.title}</strong><small>{release.book_count} 本书 · {release.card_count} 张卡 · 版本 {release.content_version.slice(0, 12)}</small></span><span className="release-state">{releaseLabels[release.status]} / {rightsLabels[release.rights_status]}</span></button></li>)}</ul>
    <div className="publishing-pagination">{cursor && <button type="button" onClick={() => setCursor(null)}>返回首批版本</button>}{result.data?.next_cursor && <button type="button" onClick={() => setCursor(result.data!.next_cursor)}>下一批版本</button>}</div>
  </section>;
}
/** id与refresh绑定固定版本详情，权限仅决定呈现，后端再次核验每个动作。 */
function ReleasePanel({ id, refresh, permissions, onSaved, onClose }: { id: string; refresh: number; permissions: AdminIdentity['granted_permissions']; onSaved: () => void; onClose: () => void }) {
  const result = usePublishingRead(useCallback((signal: AbortSignal) => readManagedRelease(id, signal), [id]), refresh);
  const data = result.data;
  return <section className="publishing-section release-detail"><button className="secondary-action" type="button" onClick={onClose}>收起版本详情</button><PublishingError failure={result.failure} />{!data && !result.failure && <p role="status">正在读取版本与审核状态…</p>}{data && <><h3>{data.title}</h3><p>{data.description}</p><p>{releaseLabels[data.status]} · {rightsLabels[data.rights_status]}</p><h4>本版本的书籍与作者</h4><ul className="release-books">{data.books.map(book => <li key={book.id}><strong>{book.title}</strong><span>{book.author_display ?? '作者信息未提供'}</span></li>)}</ul>
    <h4>当前权利审核记录</h4>{data.rights_records.length ? <ul>{data.rights_records.map(right => <li key={right.id}>{rightsLabels[right.status]} · {right.basis_type} · {right.scope_book_ids.length ? `${right.scope_book_ids.length} 本书` : '整个版本'} · 用途 {right.allowed_uses.join('、') || '无'}{right.valid_until ? ` · 至 ${new Date(right.valid_until).toLocaleString('zh-CN')}` : ''}</li>)}</ul> : <p>尚无可展示的权利审核记录。</p>}
    {permissions.includes('knowledge.review') && <RightsEditor release={data} onSaved={onSaved} />}
    <PublicationActions release={data} permissions={permissions} onSaved={onSaved} />
    {permissions.includes('grants.manage') && <GrantEditor release={data} canListUsers={permissions.includes('accounts.view')} onSaved={onSaved} />}
  </>}</section>;
}
/** release为当前已读版本；发布与撤销均要求单独确认，未勾选不发送请求。 */
function PublicationActions({ release, permissions, onSaved }: { release: ManagedRelease; permissions: AdminIdentity['granted_permissions']; onSaved: () => void }) {
  const write = usePublishingWrite(), [confirmed, setConfirmed] = useState(false), [reason, setReason] = useState('');
  /** event明确提交发布；后端以当前文件、技术校验、完整权利覆盖裁定。 */
  function publish(event: FormEvent) { event.preventDefault(); if (!confirmed) return; write.submit(`publish:${release.id}`, { status: release.status }, (key, signal) => publishRelease(release.id, release.status, key, signal), () => { setConfirmed(false); onSaved(); }); }
  /** event明确撤销版本，不删历史源文件或用户问题。 */
  function revoke(event: FormEvent) { event.preventDefault(); if (!reason.trim()) return; write.submit(`revoke:${release.id}`, { status: release.status, reason }, (key, signal) => revokeRelease(release.id, release.status, reason, key, signal), () => { setReason(''); onSaved(); }); }
  return <section className="publishing-actions"><h4>3. 发布状态</h4>{permissions.includes('knowledge.publish') && release.status !== 'published' && <form onSubmit={publish}><label className="check-label"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />我已核对本版本的书籍范围及实际权利依据，确认请求发布</label><p>发布不会自动给所有用户开通访问，下一步需单独授权。</p><button type="submit" disabled={write.disabled || !confirmed || release.rights_status !== 'approved' || release.status === 'staged'}>发布知识版本</button></form>}
    {release.status === 'published' && <p>该版本已发布。若权利条件有变化，先撤销发布，停止后续访问。</p>}
    {permissions.includes('knowledge.revoke') && release.status !== 'revoked' && <form className="publishing-inline" onSubmit={revoke}><label>撤销发布的原因<input value={reason} onChange={event => setReason(event.target.value)} maxLength={500} required /></label><button className="secondary-action" type="submit" disabled={write.disabled || !reason.trim()}>撤销本版本</button></form>}<PublishingError failure={write.failure} />
  </section>;
}
