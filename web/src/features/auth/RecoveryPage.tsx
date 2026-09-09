/** 找回和确认分离；令牌只驻留本次React内存，隐藏、完成或离开即清理。 */
import { useCallback, useEffect, useLayoutEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { flushSync } from 'react-dom';
import { Link } from 'react-router-dom';
import { ApiFailure } from '../../api/client';
import { confirmPasswordReset, readRecoveryOptions, recoveryToken, requestPasswordReset } from '../../api/recovery';
import type { RecoveryOptions } from '../../api/recovery';
import { AuthShell, ErrorNotice, knownFailure, PasswordField, SubmitButton, useWriteAction } from './shared';

/** 无参数；渠道来自当前服务，不把缺失配置推定为可用。 */
function useOptions() {
  const [options, setOptions] = useState<RecoveryOptions | null>(null), [failure, setFailure] = useState<ApiFailure | null>(null), [revision, setRevision] = useState(0);
  useEffect(() => { const request = new AbortController(); setOptions(null); setFailure(null); readRecoveryOptions(request.signal).then(value => { if (!request.signal.aborted) setOptions(value); }).catch(error => { if (!request.signal.aborted) setFailure(knownFailure(error)); }); return () => request.abort(); }, [revision]);
  return { options, failure, refresh: () => setRevision(value => value + 1) };
}
/** clear为本页敏感数据清除函数，隐藏时同步执行，不复活旧令牌。 */
function useHiddenClear(clear: () => void) { useEffect(() => { const hide = () => flushSync(clear), visibility = () => { if (document.visibilityState === 'hidden') hide(); }; window.addEventListener('pagehide', hide); document.addEventListener('visibilitychange', visibility); return () => { window.removeEventListener('pagehide', hide); document.removeEventListener('visibilitychange', visibility); }; }, [clear]); }
/** failure来自固定错误代码，不显示服务器自由正文。 */
function RecoveryError({ failure }: { failure: ApiFailure | null }) {
  if (failure?.code === 'RESET_INVALID') return <p className="auth-error" role="alert">重置链接已失效或不可用，请重新申请链接。</p>;
  if (failure?.code === 'CHANNEL_UNAVAILABLE') return <p className="auth-error" role="alert">邮件渠道当前不可用，请稍后手动重试或联系管理员。</p>;
  return <ErrorNotice failure={failure} />;
}
/** state为真实能力查询；retry只重读配置，不提交任何邮箱。 */
function OptionsNotice({ state }: { state: ReturnType<typeof useOptions> }) {
  if (state.failure) return <><RecoveryError failure={state.failure} /><button className="text-action" type="button" onClick={state.refresh}>重新读取找回设置</button></>;
  if (!state.options) return <p role="status">正在确认找回渠道…</p>;
  if (!state.options.password_reset.available) return <p role="status">当前未启用密码找回，请联系部署负责人配置邮件渠道。</p>;
  return <p>{state.options.password_reset.delivery === 'local_capture' ? '本机测试模式，不会发送到你的邮箱；请由本机开发负责人取得测试链接。' : '如账号符合条件，将通过已配置的邮件渠道处理。'}链接有效期为 {Math.ceil(state.options.password_reset.token_ttl_seconds / 60)} 分钟。</p>;
}
/** 无参数；提交响应不泄露地址存在性，不自动重复发送邮件。 */
export function ForgotPasswordPage() {
  const state = useOptions(), write = useWriteAction(), [email, setEmail] = useState(''), [receipt, setReceipt] = useState<'local_capture' | 'smtp' | null>(null);
  const clear = useCallback(() => { write.cancel(); setEmail(''); setReceipt(null); }, [write.cancel]); useHiddenClear(clear);
  /** event是用户明确申请；保持通用受理措辞，不保证投递或账号存在。 */
  function submit(event: FormEvent) { event.preventDefault(); if (!state.options?.password_reset.available || !email.trim() || write.pending) return; setReceipt(null); void write.run(signal => requestPasswordReset(email, signal), result => setReceipt(result.delivery)); }
  return <AuthShell><div className="form-heading"><span className="section-label">重新回到你的书房</span><h2>找回密码</h2><p>填写账号邮箱，申请一次性重置链接。管理员账号不通过此入口恢复。</p></div><OptionsNotice state={state} />
    <form className="auth-form" onSubmit={submit} aria-busy={write.pending}><div className="auth-field"><label htmlFor="recovery-email">账号邮箱</label><input id="recovery-email" type="email" autoComplete="username" maxLength={254} required value={email} onChange={event => setEmail(event.target.value)} disabled={write.pending} /></div><RecoveryError failure={write.failure} /><SubmitButton label="申请重置链接" pending={write.pending} seconds={write.seconds} disabled={!state.options?.password_reset.available || !email.trim()} /></form>
    {receipt && <p role="status">{receipt === 'local_capture' ? '如账号符合条件，重置链接会交给本机测试捕获；不会发送到外部邮箱。' : '如账号符合条件，我们会尝试发送重置邮件；申请受理不代表邮件已送达，请稍后检查收件箱和垃圾邮件。'}</p>}<p className="auth-switch"><Link to="/login">返回登录</Link></p>
  </AuthShell>;
}
/** 无参数；只接邮件fragment，移除URL中的所有查询/片段，不能自动消费令牌。 */
export function ResetPasswordPage() {
  const [token, setToken] = useState(() => recoveryToken(window.location.hash)), [password, setPassword] = useState(''), [confirmation, setConfirmation] = useState(''), [validation, setValidation] = useState(''), [done, setDone] = useState(false);
  const state = useOptions(), write = useWriteAction();
  useLayoutEffect(() => { window.history.replaceState(window.history.state, '', window.location.pathname); }, []);
  const clear = useCallback(() => { write.cancel(); setToken(''); setPassword(''); setConfirmation(''); setValidation(''); }, [write.cancel]); useHiddenClear(clear);
  /** event为显式确认；密码原样提交，成功后要求重新登录。 */
  function submit(event: FormEvent) {
    event.preventDefault(); if (!token || !state.options?.password_reset.available || write.pending) return;
    if (password !== confirmation) { setValidation('两次输入的密码不一致。'); return; }
    const size = Array.from(password).length, limits = state.options.password;
    if (size < limits.min_length || size > limits.max_length) { setValidation(`新密码须为 ${limits.min_length} 至 ${limits.max_length} 个字符。`); return; }
    setValidation(''); void write.run(signal => confirmPasswordReset(token, password, signal), () => { setToken(''); setDone(true); }, undefined, () => { setPassword(''); setConfirmation(''); });
  }
  return <AuthShell>{done ? <><div className="form-heading"><h2>密码已更新</h2><p>旧会话已失效。请使用新密码重新登录，我们不会自动登录或恢复知识授权。</p></div><Link className="link-action" to="/login">使用新密码登录</Link></> : <><div className="form-heading"><span className="section-label">为账号设置新的钥匙</span><h2>设置新密码</h2><p>链接仅用于本次重置，请不要转发。刷新或隐藏此页面会清除当前链接，请重新从邮件打开。</p></div>
    {!token ? <p role="alert">链接缺失或已从当前页面清除，请重新打开邮件中的链接，或重新申请。</p> : <><OptionsNotice state={state} /><form className="auth-form" onSubmit={submit} aria-busy={write.pending}><PasswordField value={password} onChange={setPassword} registering minLength={state.options?.password.min_length} maxLength={state.options?.password.max_length} disabled={write.pending} /><div className="auth-field"><label htmlFor="reset-confirmation">确认新密码</label><input id="reset-confirmation" type="password" autoComplete="new-password" required maxLength={256} value={confirmation} onChange={event => setConfirmation(event.target.value)} disabled={write.pending} /></div>{validation && <p className="auth-error" role="alert">{validation}</p>}<RecoveryError failure={write.failure} /><SubmitButton label="保存新密码" pending={write.pending} seconds={write.seconds} disabled={!state.options?.password_reset.available || !password || !confirmation} /></form></>}
    <p className="auth-switch"><Link to="/forgot-password">重新申请重置链接</Link> · <Link to="/login">返回登录</Link></p></>}</AuthShell>;
}
