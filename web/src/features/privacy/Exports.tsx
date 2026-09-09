/** 个人导出从真实任务恢复；下载每次经服务端授权，Blob不进入持久存储。 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { downloadExport, readExports, requestExport } from '../../api/privacy';
import type { ExportRecord, ExportScope } from '../../api/privacy';
import { useWriteAction } from '../auth/shared';
import { PrivacyError, usePrivacyFailure, usePrivacyRead } from './shared';

export const exportScopes: Record<ExportScope, string> = { problems: '问题与对话', learning: '学习记录', all_personal: '全部个人记录' };
const exportStatuses: Record<ExportRecord['status'], string> = { queued: '等待处理', running: '正在生成', ready: '可以下载', failed: '生成未完成', expired: '已过期' };
/** 无参数；密码只保留当前输入，幂等签名仅包含scope，不包含密码或其哈希。 */
export function ExportPanel() {
  const write = useWriteAction(), reject = usePrivacyFailure(), [scope, setScope] = useState<ExportScope>('all_personal'), [password, setPassword] = useState(''), [refresh, setRefresh] = useState(0), [notice, setNotice] = useState('');
  const submission = useRef<{ scope: ExportScope; key: string } | null>(null);
  /** event是用户明确请求；失效或失败也清密码，不自动再次生成。 */
  function submit(event: FormEvent) { event.preventDefault(); if (!password || write.pending) return; if (submission.current?.scope !== scope) submission.current = { scope, key: crypto.randomUUID() }; const key = submission.current.key; void write.run(signal => requestExport(scope, password, key, signal), () => { submission.current = null; setNotice('导出请求已受理，请以下方实际任务状态为准。'); setRefresh(value => value + 1); }, reject, () => setPassword('')); }
  return <section className="privacy-panel"><h2>带走你的个人记录</h2><p>包含所选范围内的个人记录与当前许可允许导出的知识相关内容，不含原书、内部提示词或密钥。回收站中的问题及关联学习不纳入导出；权限不足的知识内容会明确省略。</p><p>导出完成后 24 小时内可下载，下载时仍须登录并通过实时权限核验。已下载到你设备的文件不会被远程收回，请妥善保存。</p>
    <form className="privacy-form" onSubmit={submit}><label>导出范围<select value={scope} onChange={event => setScope(event.target.value as ExportScope)} disabled={write.pending}>{Object.entries(exportScopes).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label>导出前验证密码<input type="password" autoComplete="current-password" maxLength={256} value={password} onChange={event => setPassword(event.target.value)} disabled={write.pending} required /></label><PrivacyError failure={write.failure} /><button type="submit" disabled={write.pending || write.seconds > 0 || !password}>{write.pending ? '正在申请…' : '生成个人数据导出'}</button></form>{notice && <p role="status">{notice}</p>}<ExportHistory refresh={refresh} />
  </section>;
}
/** refresh由实际申请结果更新，只有真实queued/running任务才轮询，不生成假进度条。 */
function ExportHistory({ refresh }: { refresh: number }) {
  const [cursor, setCursor] = useState<string | null>(null), [tick, setTick] = useState(0);
  const result = usePrivacyRead(useCallback((signal: AbortSignal) => readExports(cursor, signal), [cursor]), refresh + tick);
  const running = result.data?.items.some(item => item.status === 'queued' || item.status === 'running');
  useEffect(() => { if (!running || result.failure) return; const timer = window.setTimeout(() => setTick(value => value + 1), 2500); return () => window.clearTimeout(timer); }, [running, result.data, result.failure]);
  useEffect(() => { setCursor(null); }, [refresh]);
  return <div className="privacy-history"><div className="privacy-row"><h3>我的导出记录</h3><button className="secondary-action" type="button" onClick={() => setTick(value => value + 1)}>刷新导出状态</button></div><PrivacyError failure={result.failure} />{!result.data && !result.failure && <p role="status">正在读取导出记录…</p>}{result.data?.items.length === 0 && <p>还没有导出记录。</p>}<ul className="privacy-records">{result.data?.items.map(item => <ExportRow key={item.id} item={item} />)}</ul><div className="privacy-row">{cursor && <button className="secondary-action" type="button" onClick={() => setCursor(null)}>最新导出</button>}{result.data?.next_cursor && <button className="secondary-action" type="button" onClick={() => setCursor(result.data!.next_cursor)}>较早导出</button>}</div></div>;
}
/** item为当前本人导出；只有显式点击才读取文件，完成后释放临时URL。 */
function ExportRow({ item }: { item: ExportRecord }) {
  const write = useWriteAction(), reject = usePrivacyFailure(), [notice, setNotice] = useState('');
  const pendingUrl = useRef<string | null>(null), timer = useRef<number | null>(null);
  /** 无参数；释放本行创建的临时下载引用，不让隐藏页面保留导出正文。 */
  const release = useCallback(() => { if (timer.current !== null) window.clearTimeout(timer.current); timer.current = null; if (pendingUrl.current) URL.revokeObjectURL(pendingUrl.current); pendingUrl.current = null; }, []);
  useEffect(() => release, [release]);
  /** 无参数；服务端重新核验权限后下载，文件名只来自已校验UUID。 */
  function download() { void write.run(signal => downloadExport(item.id, item.scope, signal), blob => { release(); const url = URL.createObjectURL(blob); pendingUrl.current = url; const anchor = document.createElement('a'); anchor.href = url; anchor.download = `second-brain-personal-${item.id}.json`; document.body.append(anchor); anchor.click(); anchor.remove(); timer.current = window.setTimeout(release, 0); setNotice('文件已交给浏览器下载，请在下载列表确认保存结果。'); }, reject); }
  return <li><div className="privacy-row"><div><strong>{exportScopes[item.scope]}</strong><p>{exportStatuses[item.status]} · 申请于 {new Date(item.created_at).toLocaleString('zh-CN')}</p>{item.expires_at && <p>有效期至 {new Date(item.expires_at).toLocaleString('zh-CN')}</p>}</div>{item.status === 'ready' && <button type="button" className="secondary-action" disabled={write.pending || write.seconds > 0} onClick={download}>{write.pending ? '正在核验并下载…' : '下载 JSON 文件'}</button>}</div>{item.status === 'failed' && <p>任务未完成，可刷新核对后重新申请；不会自动重跑。</p>}<PrivacyError failure={write.failure} />{notice && <p role="status">{notice}</p>}</li>;
}
