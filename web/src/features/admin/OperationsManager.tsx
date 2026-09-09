/** 运营工作台按明确权限分区；只展示聚合，不读取用户对话和反馈正文。 */
import { useCallback, useState } from 'react';
import type { FormEvent } from 'react';
import type { AdminIdentity } from '../../api/admin';
import { ApiFailure } from '../../api/client';
import { createInvitation, readFeedbackSummary, readOperations } from '../../api/adminops';
import type { FeedbackCategory, InvitationDelivery, JobStatus } from '../../api/adminops';
import { PublishingError, PublishingFailure, usePublishingRead, usePublishingWrite } from './publishing-shared';
import { AccountOperations } from './AccountOperations';
import '../../styles/publishing.css';
import '../../styles/operations.css';

export const operationsPermissions = ['accounts.view', 'accounts.disable', 'accounts.invite', 'quota.manage', 'operations.view', 'feedback.review'] as const;
const jobLabels: Record<JobStatus, string> = { queued: '排队中', running: '执行中', cancel_requested: '正在取消', succeeded: '已完成', failed: '未完成', cancelled: '已取消' };
const feedbackLabels: Record<FeedbackCategory, string> = { helpful: '有帮助', shallow: '建议太浅', unclear_principle: '原理不清楚', wrong_source: '来源有问题', other: '其他反馈' };
/** identity是当前管理身份，onFailure销毁失效或已撤销权限的管理页面。 */
export function OperationsManager({ identity, onFailure }: { identity: AdminIdentity; onFailure: (error: ApiFailure) => void }) {
  const [revision, setRevision] = useState(0), permissions = identity.granted_permissions;
  const reject = useCallback((error: ApiFailure) => { if (error.status === 401 || error.code === 'ADMIN_PERMISSION_DENIED') onFailure(error); }, [onFailure]);
  if (!operationsPermissions.some(permission => permissions.includes(permission))) return <section className="admin-panel"><h2>运营工作台</h2><p>此账号尚未获得运营管理权限。</p></section>;
  return <PublishingFailure.Provider value={reject}><section className="publishing-main operations-main"><header className="publishing-header"><div><p className="section-label">账号与服务运营</p><h2>运营工作台</h2><p>管理访问与资源，观察真实运行情况。这里不提供用户聊天、模型提示词或反馈正文的浏览入口。</p></div><button type="button" className="secondary-action" onClick={() => setRevision(value => value + 1)}>刷新统计</button></header>
    <div className="operations-summaries">{permissions.includes('operations.view') && <TaskSummary refresh={revision} />}{permissions.includes('feedback.review') && <FeedbackSummary refresh={revision} />}</div>
    {permissions.some(value => value === 'accounts.view' || value === 'accounts.disable' || value === 'quota.manage') && <AccountOperations permissions={permissions} />}
    {permissions.includes('accounts.invite') && <InvitationPanel />}
  </section></PublishingFailure.Provider>;
}
/** refresh是人工刷新计数；按服务器返回的UTC月标注，不绘制虚构趋势。 */
function TaskSummary({ refresh }: { refresh: number }) {
  const result = usePublishingRead(readOperations, refresh);
  return <section className="admin-panel operations-summary"><h3>任务运行</h3><PublishingError failure={result.failure} />{result.data ? <><p>{result.data.period.slice(0, 7)} · UTC 月度任务</p><p className="operations-total"><strong>{result.data.total_runs}</strong> 次任务</p><dl>{result.data.run_counts.map(row => <div key={row.status}><dt>{jobLabels[row.status]}</dt><dd>{row.count}</dd></div>)}</dl>{result.data.total_runs === 0 && <p>本月暂无任务记录。</p>}</> : !result.failure && <p role="status">正在读取任务统计…</p>}</section>;
}
/** refresh用于重新读取全部历史反馈分类；不请求具体评论。 */
function FeedbackSummary({ refresh }: { refresh: number }) {
  const result = usePublishingRead(readFeedbackSummary, refresh);
  return <section className="admin-panel operations-summary"><h3>答案反馈</h3><PublishingError failure={result.failure} />{result.data ? <><p>全部历史 · 分类统计</p><p className="operations-total"><strong>{result.data.total_feedback}</strong> 条反馈</p><dl>{result.data.category_counts.map(row => <div key={row.category}><dt>{feedbackLabels[row.category]}</dt><dd>{row.count}</dd></div>)}</dl>{result.data.total_feedback === 0 && <p>尚无反馈，不据此判断回答质量。</p>}</> : !result.failure && <p role="status">正在读取反馈统计…</p>}</section>;
}
/** 无参数；生成本机捕获邀请，公开页面仅展示安全回执。 */
function InvitationPanel() {
  const [email, setEmail] = useState(''), [delivery, setDelivery] = useState<InvitationDelivery | null>(null), write = usePublishingWrite();
  /** event为明确邀请请求；未确认结果不清邮箱，手动重试复用幂等键。 */
  function submit(event: FormEvent) { event.preventDefault(); write.submit('invitation', { email }, (key, signal) => createInvitation(email, key, signal), value => { setDelivery(value); setEmail(''); }); }
  return <section className="publishing-section"><h3>邀请新读者</h3><p>当前为本机捕获交付：由部署负责人从私有目录取出邀请并转交对应收件人。网页不展示邀请令牌。</p><form className="publishing-inline" onSubmit={submit}><label>邀请邮箱<input type="email" autoComplete="off" maxLength={254} value={email} onChange={event => setEmail(event.target.value)} disabled={write.disabled} required /></label><button type="submit" disabled={write.disabled || !email.trim()}>生成本机邀请</button></form><PublishingError failure={write.failure} />{delivery && <div className="operations-notice" role="status"><strong>本机邀请已生成；未发送邮件。</strong><p>投递编号：<code>{delivery.delivery_id}</code></p><p>有效期至 {new Date(delivery.expires_at).toLocaleString('zh-CN')}。请由部署负责人按编号取件并安全交付。</p></div>}</section>;
}
