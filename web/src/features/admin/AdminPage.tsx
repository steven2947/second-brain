/** 管理入口与普通书房分离；身份保护完成后才显示显式权限，默认不查询用户内容。 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import type { FormEvent, ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ShieldCheckIcon } from '@phosphor-icons/react';
import { adminPermissionLabels, loginAdmin, logoutAdmin, readAdmin, reauthAdmin } from '../../api/admin';
import type { AdminIdentity, AdminLogin, AdminPermission } from '../../api/admin';
import { ApiFailure } from '../../api/client';
import { knownFailure, useWriteAction } from '../auth/shared';
import { KnowledgeManager } from './KnowledgeManager';
import { OperationsManager, operationsPermissions } from './OperationsManager';
import '../../styles/admin.css';

/** children为本次管理页；不在公共导航加入管理入口或暴露用户内容。 */
function AdminShell({ children }: { children: ReactNode }) { return <div className="product-shell admin-shell"><a className="skip-link" href="#main-content">跳转到主要内容</a><header className="product-header"><span className="product-brand"><ShieldCheckIcon size={26} aria-hidden="true" />第二大脑 · 管理</span><Link to="/login">普通账号入口</Link></header><main id="main-content" className="admin-main">{children}</main><footer className="product-footer"><span>独立管理入口</span><span>最小权限 · 重要操作重新认证</span></footer></div>; }
/** error只映射固定代码；不回显远端错误内容或身份枚举细节。 */
function AdminError({ error }: { error: ApiFailure | null }) {
  if (!error) return null;
  return <p className="auth-error" role="alert">{error.status === 429 ? '尝试过于频繁，请等待后再试。' : error.code === 'ADMIN_REAUTH_REQUIRED' ? '请重新验证密码和验证码，再继续管理操作。' : error.code === 'ADMIN_PERMISSION_DENIED' ? '当前账号没有执行该操作的管理权限。' : error.code === 'INVALID_CREDENTIALS' ? '账号、密码或验证码不匹配，或账号当前不可用。请重新输入凭据。' : error.code === 'CSRF_FAILED' ? '请求校验未通过，请重新操作。' : '请求暂未完成，请稍后再试。未自动重复提交。'}</p>;
}
/** method/token/onMethod/onToken用于当前单次表单；切换方式清掉旧验证码。 */
function TokenInput({ method, token, onMethod, onToken, disabled }: { method: AdminLogin['method']; token: string; onMethod: (value: AdminLogin['method']) => void; onToken: (value: string) => void; disabled: boolean }) {
  return <><label>验证方式<select value={method} onChange={event => { onMethod(event.target.value as AdminLogin['method']); onToken(''); }} disabled={disabled}><option value="totp">认证器动态验证码</option><option value="recovery">离线恢复码（单次使用）</option></select></label><label>{method === 'totp' ? '动态验证码' : '恢复码'}<input type={method === 'totp' ? 'text' : 'password'} inputMode={method === 'totp' ? 'numeric' : 'text'} autoComplete={method === 'totp' ? 'one-time-code' : 'off'} pattern={method === 'totp' ? '[0-9]{6}' : undefined} maxLength={method === 'totp' ? 6 : 128} value={token} onChange={event => onToken(event.target.value)} disabled={disabled} required /></label>{method === 'recovery' && <p className="field-help">此恢复码验证成功后即失效。不会在页面重新展示或保存它。</p>}</>;
}
/** clear为敏感输入清理函数，cancel终止当前写请求；隐藏时同步清理避免晚响应恢复。 */
function useClearOnHide(clear: () => void, cancel: () => void) {
  useEffect(() => {
    /** 无参数；冻结前取消请求，再同步清空凭据。 */
    function hide() { cancel(); flushSync(clear); }
    /** 无参数；后台标签与离开页面采用相同处理。 */
    function visibility() { if (document.visibilityState === 'hidden') hide(); }
    window.addEventListener('pagehide', hide); document.addEventListener('visibilitychange', visibility);
    return () => { window.removeEventListener('pagehide', hide); document.removeEventListener('visibilitychange', visibility); };
  }, [clear, cancel]);
}
/** 无参数；独立双因素登录，首个管理员必须已在本机登记确认设备。 */
export function AdminLoginPage() {
  const navigate = useNavigate(), write = useWriteAction();
  const [email, setEmail] = useState(''), [password, setPassword] = useState(''), [token, setToken] = useState(''), [method, setMethod] = useState<AdminLogin['method']>('totp');
  const clear = useCallback(() => { setPassword(''); setToken(''); }, []); useClearOnHide(clear, write.cancel);
  /** event为显式表单提交；成功与失败都清空密码及OTP，不进行自动补交。 */
  function submit(event: FormEvent) { event.preventDefault(); void write.run(signal => loginAdmin({ email, password, token, method }, signal), () => navigate('/admin', { replace: true }), undefined, clear); }
  return <AdminShell><section className="admin-login-panel"><p className="section-label">受保护的管理入口</p><h1>验证身份，再进入管理。</h1><p>使用管理员密码与认证器动态验证码。只有已登记、已确认的设备才能登录。</p><form className="admin-form" onSubmit={submit} aria-busy={write.pending}>
    <label>管理员邮箱<input type="email" autoComplete="username" maxLength={254} value={email} onChange={event => setEmail(event.target.value)} disabled={write.pending} required /></label>
    <label>管理员密码<input type="password" autoComplete="current-password" maxLength={256} value={password} onChange={event => setPassword(event.target.value)} disabled={write.pending} required /></label>
    <TokenInput method={method} token={token} onMethod={setMethod} onToken={setToken} disabled={write.pending} /><AdminError error={write.failure} />
    <button type="submit" disabled={write.pending || write.seconds > 0}>{write.pending ? '正在验证…' : write.seconds ? `${write.seconds} 秒后可重试` : '验证并进入管理'}</button>
  </form><p className="admin-note">首次管理员登记由部署者在本机完成。网页不提供自助提权、关闭 MFA 或找回设备秘密的入口。</p></section></AdminShell>;
}
/** 无参数；每次进入/恢复检查真实管理会话，权限或设备失效后不保留管理数据。 */
export function AdminPage({ knowledge = false, operations = false }: { knowledge?: boolean; operations?: boolean }) {
  const navigate = useNavigate(), identityRequest = useRef<AbortController | null>(null);
  const [identity, setIdentity] = useState<AdminIdentity | null>(null), [error, setError] = useState<ApiFailure | null>(null), [retry, setRetry] = useState(0);
  const fail = useCallback((value: unknown) => { const safe = knownFailure(value); setIdentity(null); setError(safe); if (safe.status === 401) navigate('/admin/login', { replace: true }); }, [navigate]);
  useEffect(() => {
    let suspended = document.visibilityState === 'hidden';
    /** 无参数；身份成功前不请求管理对象，晚到数据不会挂入新身份。 */
    function verify() { if (document.visibilityState === 'hidden') return; suspended = false; identityRequest.current?.abort(); const request = new AbortController(); identityRequest.current = request; setIdentity(null); setError(null); readAdmin(request.signal).then(value => { if (!request.signal.aborted) setIdentity(value); }).catch(error => { if (!request.signal.aborted) fail(error); }); }
    /** 无参数；同步销毁管理页及再认证凭据。 */
    function hide() { suspended = true; identityRequest.current?.abort(); flushSync(() => { setIdentity(null); setError(null); }); }
    /** 无参数；恢复前重读当前权限与MFA设备状态。 */
    function restore() { if (suspended) verify(); }
    /** 无参数；处理标签可见性变化。 */
    function visibility() { if (document.visibilityState === 'hidden') hide(); else restore(); }
    if (!suspended) verify(); window.addEventListener('pagehide', hide); window.addEventListener('pageshow', restore); document.addEventListener('visibilitychange', visibility);
    return () => { identityRequest.current?.abort(); window.removeEventListener('pagehide', hide); window.removeEventListener('pageshow', restore); document.removeEventListener('visibilitychange', visibility); };
  }, [retry, fail]);
  return <AdminShell>{identity ? <AdminWorkspace knowledge={knowledge} operations={operations} identity={identity} onVerified={setIdentity} onFailure={fail} /> : error ? <section className="reading-empty"><h1>暂时无法进入管理</h1><AdminError error={error} /><button type="button" onClick={() => setRetry(value => value + 1)}>重新验证身份</button></section> : <p role="status">正在确认管理身份与权限…</p>}</AdminShell>;
}
/** identity是当前服务器投影，onVerified更新再认证结果，onFailure销毁失效身份。 */
function AdminWorkspace({ identity, onVerified, onFailure, knowledge, operations }: { identity: AdminIdentity; onVerified: (value: AdminIdentity) => void; onFailure: (error: ApiFailure) => void; knowledge: boolean; operations: boolean }) {
  const navigate = useNavigate(), write = useWriteAction(), [password, setPassword] = useState(''), [token, setToken] = useState(''), [method, setMethod] = useState<AdminLogin['method']>('totp'), [notice, setNotice] = useState('');
  const clear = useCallback(() => { setPassword(''); setToken(''); }, []); useClearOnHide(clear, write.cancel);
  /** error为后台鉴权失败，不把后台401导航到普通登录页。 */
  function reject(error: ApiFailure) { if (error.code === 'ADMIN_AUTH_REQUIRED' || error.code === 'ADMIN_PERMISSION_DENIED') onFailure(error); }
  /** event提交同一管理员的完整双因素再次认证。 */
  function reauth(event: FormEvent) { event.preventDefault(); void write.run(signal => reauthAdmin(identity.user.id, { password, token, method }, signal), value => { onVerified(value); setNotice('已重新验证身份。'); }, reject, clear); }
  return <><header className="admin-heading"><div><p className="section-label">管理身份已验证</p><h1>{identity.user.display_name}</h1><p>{identity.user.email}</p></div><button className="secondary-action" type="button" disabled={write.pending || write.seconds > 0} onClick={() => void write.run(logoutAdmin, () => navigate('/admin/login', { replace: true }), reject, clear)}>退出管理</button></header>
    <nav className="admin-navigation" aria-label="管理导航"><Link to="/admin" aria-current={!knowledge && !operations ? 'page' : undefined}>管理身份</Link>{identity.granted_permissions.some(value => value.startsWith('knowledge.') || value === 'grants.manage') && <Link to="/admin/knowledge" aria-current={knowledge ? 'page' : undefined}>知识版本与授权</Link>}{operationsPermissions.some(value => identity.granted_permissions.includes(value)) && <Link to="/admin/operations" aria-current={operations ? 'page' : undefined}>账号与运营</Link>}</nav>
    <div className={`admin-work-grid ${knowledge || operations ? 'admin-knowledge-grid' : ''}`}>{knowledge ? <KnowledgeManager identity={identity} onFailure={onFailure} /> : operations ? <OperationsManager identity={identity} onFailure={onFailure} /> : <section className="admin-panel"><p className="section-label">当前账号的显式授权</p><h2>权限范围</h2><p>以下是账号已获授的权限，不代表所有管理模块都已开放。管理员身份不会自动获得用户聊天正文的读取权。</p>
      {identity.granted_permissions.length ? <ul className="admin-permissions">{identity.granted_permissions.map(permission => <li key={permission}><ShieldCheckIcon size={17} aria-hidden="true" /><span>{adminPermissionLabels[permission as AdminPermission]}</span><code>{permission}</code></li>)}</ul> : <p role="status">此账号尚未配置具体管理权限。</p>}
      <div className="admin-note"><strong>管理按显式权限分区。</strong><p>“知识版本与授权”管理导入、审核和发布；“账号与运营”管理普通账号、次数额度与邀请。统计不包含用户聊天正文。</p></div>
    </section>}<section className="admin-panel"><h2>重要操作前重新认证</h2><dl className="admin-session"><dt>本次验证时间</dt><dd>{new Date(identity.verified_at).toLocaleString('zh-CN')}</dd><dt>敏感操作验证时效至</dt><dd>{new Date(identity.fresh_until).toLocaleString('zh-CN')}</dd><dt>管理会话最晚到期</dt><dd>{new Date(identity.session_expires_at).toLocaleString('zh-CN')}</dd></dl>
      <form className="admin-form" onSubmit={reauth}><label>再次输入密码<input type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} maxLength={256} disabled={write.pending} required /></label><TokenInput method={method} token={token} onMethod={setMethod} onToken={setToken} disabled={write.pending} /><AdminError error={write.failure} />{notice && <p role="status">{notice}</p>}<button type="submit" disabled={write.pending || write.seconds > 0}>{write.pending ? '正在验证…' : write.seconds ? `${write.seconds} 秒后可重试` : '重新验证管理身份'}</button></form>
    </section></div>
  </>;
}
