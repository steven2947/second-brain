/** 管理操作共用读写生命周期；读可刷新，写只在显式点击时发送。 */
import { createContext, useContext, useEffect, useRef, useState } from 'react';
import { ApiFailure } from '../../api/client';
import { knownFailure, useWriteAction } from '../auth/shared';

export const PublishingFailure = createContext<(error: ApiFailure) => void>(() => {});
/** load读取当前对象；refresh来自明确刷新或成功写回，不改变提交内容。 */
export function usePublishingRead<T>(load: (signal: AbortSignal) => Promise<T>, refresh = 0) {
  const reject = useContext(PublishingFailure), rejectRef = useRef(reject); rejectRef.current = reject;
  const previousLoad = useRef<typeof load | null>(null);
  const [data, setData] = useState<T | null>(null), [failure, setFailure] = useState<ApiFailure | null>(null);
  useEffect(() => {
    const controller = new AbortController(); if (previousLoad.current !== load) setData(null); previousLoad.current = load; setFailure(null);
    load(controller.signal).then(value => { if (!controller.signal.aborted) setData(value); }).catch(error => { if (!controller.signal.aborted) { const safe = knownFailure(error); setFailure(safe); rejectRef.current(safe); } });
    return () => controller.abort();
  }, [load, refresh]);
  return { data, failure };
}
/** 无参数；相同动作和载荷的手动重试保留幂等键，成功后才释放该键。 */
export function usePublishingWrite() {
  const write = useWriteAction(), reject = useContext(PublishingFailure), submission = useRef<{ signature: string; key: string } | null>(null);
  /** action/body限定提交语义，operation是真实API调用，done只接已确认成功。 */
  function submit<T>(action: string, body: unknown, operation: (key: string, signal: AbortSignal) => Promise<T>, done: (value: T) => void) {
    if (write.pending || write.seconds) return;
    const signature = JSON.stringify([action, body]);
    if (submission.current?.signature !== signature) submission.current = { signature, key: crypto.randomUUID() };
    const key = submission.current.key;
    void write.run(signal => operation(key, signal), value => { submission.current = null; done(value); }, reject);
  }
  return { ...write, submit, disabled: write.pending || write.seconds > 0 };
}
/** failure为固定错误码，不展示路径、服务端堆栈或原始证明。 */
export function PublishingError({ failure }: { failure: ApiFailure | null }) {
  if (!failure) return null;
  const explanations: Record<string, string> = { RELEASE_NOT_READY: '暂不满足发布或授权条件：请核对技术状态、全部书籍的有效浏览许可和证明文件。', RELEASE_MUST_REVOKE: '该版本正在发布中，需先撤销发布才能重新审核权利。', PROOF_REQUIRED: '这种权利依据需要实际授权证明，请填写私有目录中已存在的证明存储键。', PROOF_UNAVAILABLE: '未找到可使用的证明文件，请核对本机存储键；不要填网址或绝对路径。', INVALID_RIGHTS_SCOPE: '权利记录包含本版本以外或重复的书籍，请重新选择适用范围。', INVALID_QUOTE_POLICY: '允许原文短引时，需要填写有效的单段字符上限。', INVALID_EXPIRY: '授权截止时间必须在未来，请核对日期和本地时间。', SOURCE_NOT_REGISTERED: '来源尚未登记，请由部署负责人登记后刷新本页。', SOURCE_UNAVAILABLE: '本机来源暂不可用，请核对固定版本、登记指纹及导入容量限制。' };
  const operationsExplanations: Record<string, string> = { STATUS_CONFLICT: '账号当前状态与你提交的状态不一致。请刷新账号列表、重新选择目标并核对后操作。', REVISION_CONFLICT: '额度已被其他操作或任务更新。请重新读取本月额度，再填写上限。', QUOTA_BELOW_USAGE: '上限不能低于当前已结算与执行中预留的次数，请重新读取额度。', ACCOUNT_EXISTS: '此邮箱已有账号，请使用现有账号管理流程，不重复生成邀请。', INVITATION_DELIVERY_UNAVAILABLE: '本机私有投递暂不可用，请由部署负责人检查私有目录后再手动重试。', NOT_FOUND: '目标不存在或当前不可操作，请核对目标编号及状态。' };
  const message = explanations[failure.code] ?? operationsExplanations[failure.code] ?? (failure.code === 'ADMIN_REAUTH_REQUIRED' ? '验证时效已过，请在右侧重新验证管理身份，再手动提交。'
    : failure.status === 409 ? '版本或提交状态已变化。请先刷新记录，再核对后操作。'
    : failure.status === 400 ? '填写内容或当前版本不符合操作条件，请检查审核记录与状态。'
    : failure.status === 429 ? '操作频率受限，请等待后再手动重试。'
    : failure.status === 403 ? '当前账号没有此操作的管理权限。'
    : '请求尚未确认完成。可先刷新记录；相同内容手动重试会沿用原提交编号。');
  return <p className="auth-error" role="alert">{message}</p>;
}
