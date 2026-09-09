/** 回收站与账号注销分别处理；不把受理或软删除展示为物理清理完成。 */
import { useCallback, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiFailure } from '../../api/client';
import { readTrash, requestDeletion, restoreProblem, trashProblem } from '../../api/privacy';
import type { DeletionReceipt, TrashRecord } from '../../api/privacy';
import { useWriteAction } from '../auth/shared';
import { PrivacyError, usePrivacyFailure, usePrivacyRead } from './shared';

/** onAccepted仅在服务器受理并停用当前账号后卸载个人页面。 */
export function DeletionPanel({ onAccepted }: { onAccepted: (value: DeletionReceipt) => void }) {
  const write = useWriteAction(), reject = usePrivacyFailure(), [password, setPassword] = useState(''), [confirmation, setConfirmation] = useState(''), [understood, setUnderstood] = useState(false);
  /** event是明确申请，必须核对确认文字；失败也清密码，不自动再次提交。 */
  function submit(event: FormEvent) { event.preventDefault(); if (!understood || confirmation !== '删除我的账号') return; void write.run(signal => requestDeletion(password, confirmation, signal), onAccepted, reject, () => setPassword('')); }
  return <section className="privacy-panel privacy-danger"><h2>注销账号</h2><p>先导出需要保留的内容。注销有 7 天冷静期：申请后账号立即停止访问，正在执行的任务不能再发布结果；期满后进入在线个人数据清理。</p>
    <details onToggle={event => { if (!event.currentTarget.open) { setPassword(''); setConfirmation(''); setUnderstood(false); } }}><summary>了解并申请注销账号</summary><div className="privacy-disclosure"><p>在线清理包含个人问题、对话、学习、收藏、行动与导出文件。共享书籍和知识审批历史不会随你的账号删除；必要记录会去除直接身份信息。</p><p>备份按保留周期过期，恢复备份时必须重新执行删除清单，不会承诺瞬间抹除所有备份或已下载文件。需要在冷静期内取消，请联系此服务的部署负责人进行身份核验。</p></div>
      <form className="privacy-form" onSubmit={submit}><label>注销前验证密码<input type="password" autoComplete="current-password" maxLength={256} value={password} onChange={event => setPassword(event.target.value)} disabled={write.pending} required /></label><label>输入“删除我的账号”确认<input autoComplete="off" value={confirmation} onChange={event => setConfirmation(event.target.value)} maxLength={20} disabled={write.pending} required /></label><label className="privacy-check"><input type="checkbox" checked={understood} onChange={event => setUnderstood(event.target.checked)} disabled={write.pending} />我理解账号将立即停止访问，且需要先自行保存重要记录</label><PrivacyError failure={write.failure} /><button type="submit" disabled={write.pending || write.seconds > 0 || !password || confirmation !== '删除我的账号' || !understood}>{write.pending ? '正在提交注销申请…' : '确认申请注销'}</button></form>
    </details>
  </section>;
}
/** 无参数；仅列本人的已删除问题元数据，恢复在服务端核对30天期限。 */
export function TrashList() {
  const [cursor, setCursor] = useState<string | null>(null), [revision, setRevision] = useState(0);
  const result = usePrivacyRead(useCallback((signal: AbortSignal) => readTrash(cursor, signal), [cursor]), revision);
  return <section className="privacy-panel"><div className="privacy-row"><h2>暂存的已删除问题</h2><button className="secondary-action" type="button" onClick={() => setRevision(value => value + 1)}>刷新回收站</button></div><p>删除后 30 天内可恢复，到期后进入清理。这里不展示已删除问题的对话和答案；恢复为归档，不会恢复知识授权，也不会重新运行旧任务。</p><PrivacyError failure={result.failure} />{!result.data && !result.failure && <p role="status">正在读取回收站…</p>}{result.data?.items.length === 0 && <p>回收站是空的。</p>}<ul className="privacy-records">{result.data?.items.map(item => <TrashRow key={`${item.id}:${item.revision}`} item={item} />)}</ul><div className="privacy-row">{cursor && <button type="button" className="secondary-action" onClick={() => setCursor(null)}>回到首批记录</button>}{result.data?.next_cursor && <button type="button" className="secondary-action" onClick={() => setCursor(result.data!.next_cursor)}>下一批记录</button>}</div></section>;
}
/** item为本人回收站快照，成功后仅提示真实恢复结果，不自动发起分析。 */
function TrashRow({ item }: { item: TrashRecord }) {
  const write = useWriteAction(), reject = usePrivacyFailure(), [restored, setRestored] = useState(false);
  return <li><div className="privacy-row"><div><strong>{item.title}</strong><p>移入时间：{new Date(item.deleted_at).toLocaleString('zh-CN')}</p><p>恢复期限至：{new Date(item.purge_after).toLocaleString('zh-CN')}</p></div>{!restored && <button className="secondary-action" type="button" disabled={write.pending || write.seconds > 0 || write.failure?.status === 409} onClick={() => void write.run(signal => restoreProblem(item.id, item.revision, signal), () => setRestored(true), reject)}>恢复为归档问题</button>}</div><PrivacyError failure={write.failure} />{restored && <p role="status">已恢复到归档。<Link to={`/app/problems/${item.id}`}>查看恢复的问题</Link>；知识访问仍以当前授权为准。</p>}</li>;
}
/** id/revision来自当前问题；disabled避免与重读竞争，onFailure交回原问题身份边界。 */
export function TrashProblemControl({ id, revision, disabled, onFailure }: { id: string; revision: number; disabled: boolean; onFailure: (error: ApiFailure) => void }) {
  const navigate = useNavigate(), write = useWriteAction(), [confirmed, setConfirmed] = useState(false);
  return <details className="privacy-delete-problem"><summary>删除这个问题</summary><p>移入回收站后，对话、答案与关联学习不可访问，正在执行的任务会停止。30 天内可从回收站恢复。</p><label className="privacy-check"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} disabled={disabled || write.pending} />确认将这个问题移入回收站</label><PrivacyError failure={write.failure} /><button className="secondary-action" type="button" disabled={disabled || write.pending || write.seconds > 0 || !confirmed || write.failure?.status === 409} onClick={() => void write.run(signal => trashProblem(id, revision, signal), () => navigate('/app/trash', { replace: true }), error => { if (error.code === 'AUTH_REQUIRED') onFailure(error); })}>移入回收站</button>{write.failure?.status === 409 && <p>请先刷新问题详情，核对新的修订后再删除。</p>}</details>;
}
