/** 隐私页只向当前身份呈现数据；错误只映射固定公开代码。 */
import { createContext, useContext, useEffect, useState } from 'react';
import { ApiFailure } from '../../api/client';
import { knownFailure } from '../auth/shared';
export const PrivacyFailure = createContext<(error: ApiFailure) => void>(() => {});
/** 无参数；供隐私子组件处理当前会话失效。 */
export function usePrivacyFailure() { return useContext(PrivacyFailure); }
/** load是稳定且已授权读取，refresh仅触发主动或真实任务状态轮询。 */
export function usePrivacyRead<T>(load: (signal: AbortSignal) => Promise<T>, refresh = 0) {
  const reject = usePrivacyFailure(), [result, setResult] = useState<{ load: typeof load; data: T } | null>(null), [failure, setFailure] = useState<ApiFailure | null>(null);
  useEffect(() => { const request = new AbortController(); setFailure(null); load(request.signal).then(data => { if (!request.signal.aborted) setResult({ load, data }); }).catch(error => { if (!request.signal.aborted) { const safe = knownFailure(error); setFailure(safe); reject(safe); } }); return () => request.abort(); }, [load, refresh, reject]);
  return { data: result?.load === load ? result.data : null, failure };
}
/** failure为实际受控响应，不回显服务器正文。 */
export function PrivacyError({ failure }: { failure: ApiFailure | null }) {
  if (!failure) return null;
  const messages: Record<string, string> = { INVALID_CREDENTIALS: '密码验证未通过，请重新输入当前密码。', REVISION_CONFLICT: '问题已被另一处更新，请刷新后核对，再操作。', EXPORT_EXPIRED: '这个导出已过期，请重新申请生成。', EXPORT_UNAVAILABLE: '导出暂不可下载，可能权限或原记录已有变化，请刷新后重新申请。', EXPORT_NOT_READY: '导出还没有准备好，请等待实际任务完成。', AUTH_REQUIRED: '登录状态已失效，请重新登录。', INVALID_INPUT: '请核对填写范围、密码和确认内容。' };
  Object.assign(messages, { TRASH_EXPIRED: '这个问题已超过 30 天恢复期限，无法再恢复。', EXPORT_STALE: '原记录或知识权限已变化，请重新申请导出。', EXPORT_TOO_LARGE: '导出超过单次容量，请改选问题或学习记录；若仍失败，请联系管理员。', EXPORT_LIMIT: '已有多个导出任务处理中，请等它们结束后再申请。' });
  const message = messages[failure.code] ?? (failure.status === 404 ? '记录不存在、已失效或当前不可访问。' : failure.status === 409 ? '数据或权限已变化，请刷新记录后再操作。' : failure.status === 429 ? '操作过于频繁，请稍后再手动重试。' : '暂时无法确认处理结果，请刷新记录或手动重试；不会自动重复提交。');
  return <p className="auth-error" role="alert">{message}</p>;
}
