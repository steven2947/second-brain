/** 普通用户登录页：真实会话、不缓存密码、不自动重试写操作。 */
import { useEffect, useState } from 'react';
import { flushSync } from 'react-dom';
import type { FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { login } from '../../api/auth';
import { safeReturnPath } from './navigation';
import { AuthShell, ErrorNotice, PasswordField, SubmitButton, useWriteAction } from './shared';

/** initialEmail仅从本次注册成功的内存状态传入，不写URL或浏览器存储。 */
export function LoginPage({ initialEmail = '', onEmailUsed }: { initialEmail?: string; onEmailUsed?: () => void }) {
  const [email, setEmail] = useState(initialEmail);
  const [password, setPassword] = useState('');
  const [validation, setValidation] = useState('');
  const action = useWriteAction();
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => { onEmailUsed?.(); }, [onEmailUsed]);
  useEffect(() => {
    /** 无参数；页面冻结前同步清空密码，取消写请求且忽略迟到结果。 */
    function hide() { action.cancel(); flushSync(() => { setPassword(''); setValidation(''); }); }
    /** 无参数；切走标签页也视为敏感输入生命周期结束。 */
    function visibility() { if (document.visibilityState === 'hidden') hide(); }
    window.addEventListener('pagehide', hide);
    document.addEventListener('visibilitychange', visibility);
    return () => { window.removeEventListener('pagehide', hide); document.removeEventListener('visibilitychange', visibility); };
  }, [action.cancel]);
  /** event为浏览器表单提交；密码按原始输入发送。 */
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (Array.from(email.trim()).length > 254 || Array.from(password).length > 256) {
      setValidation('邮箱最多 254 个字符，密码最多 256 个字符。'); return;
    }
    setValidation('');
    void action.run(signal => login({ email, password }, signal), () => {
      navigate(safeReturnPath(new URLSearchParams(location.search).get('next')), { replace: true });
    }, undefined, () => setPassword(''));
  }
  return <AuthShell><div className="form-heading"><span className="section-label">你的阅读与思考，从这里继续</span><h2>欢迎回来</h2><p>登录第二大脑，进入你的账号。</p></div>
    <form className="auth-form" onSubmit={submit} aria-busy={action.pending}>
      <div className="auth-field"><label htmlFor="email">邮箱</label><input id="email" name="email" type="email" autoComplete="username" required
        value={email} onChange={event => setEmail(event.target.value)} disabled={action.pending} placeholder="你的邮箱地址" /></div>
      <PasswordField value={password} onChange={setPassword} disabled={action.pending} />
      {validation && <p className="auth-error" role="alert">{validation}</p>}
      <ErrorNotice failure={action.failure} />
      <SubmitButton pending={action.pending} seconds={action.seconds} label="登录" />
    </form>
    <p className="auth-switch">首次来访？<Link to="/register">使用邀请注册</Link></p>
    <div className="auth-footnote"><p><Link to="/forgot-password">忘记密码？查看找回方式</Link></p><p>管理账号使用独立的多因素认证入口。</p></div>
  </AuthShell>;
}
