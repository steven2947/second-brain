/** 以真实公开选项驱动邀请注册，政策读取失败时关闭提交。 */
import { useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircleIcon } from '@phosphor-icons/react';
import { readAuthOptions, register } from '../../api/auth';
import type { AuthOptions } from '../../api/auth';
import { ApiFailure } from '../../api/client';
import { AuthShell, ErrorNotice, PasswordField, SubmitButton, knownFailure, useWriteAction } from './shared';

/** onLogin仅传递成功注册邮箱到父级内存，随后切换登录页。 */
export function RegisterPage({ onLogin }: { onLogin: (email: string) => void }) {
  const [options, setOptions] = useState<AuthOptions | null>(null);
  const [optionFailure, setOptionFailure] = useState<ApiFailure | null>(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [invite, setInvite] = useState('');
  const [password, setPassword] = useState('');
  const [accepted, setAccepted] = useState({ terms: false, privacy: false });
  const [created, setCreated] = useState(false);
  const [validation, setValidation] = useState('');
  const optionRequest = useRef<AbortController | null>(null);
  const needsReload = useRef(false);
  const action = useWriteAction();
  useEffect(() => {
    const controller = new AbortController();
    optionRequest.current = controller;
    setLoading(true); setOptionFailure(null); setOptions(null); setAccepted({ terms: false, privacy: false });
    readAuthOptions(controller.signal).then(value => { if (!controller.signal.aborted) setOptions(value); })
      .catch(error => { if (!controller.signal.aborted) setOptionFailure(knownFailure(error)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [revision]);
  useEffect(() => {
    /** 无参数；页面冻结前同步清敏感表单，并取消政策读取与注册提交。 */
    function hide() {
      needsReload.current = true;
      optionRequest.current?.abort(); action.cancel();
      flushSync(() => {
        setPassword(''); setInvite(''); setAccepted({ terms: false, privacy: false });
        setOptions(null); setLoading(true); setOptionFailure(null); setValidation('');
      });
    }
    /** 无参数；一轮恢复只触发一次政策重读，避免pageshow与visibility重复请求。 */
    function restore() {
      if (!needsReload.current || document.visibilityState === 'hidden') return;
      needsReload.current = false;
      setRevision(value => value + 1);
    }
    /** 无参数；隐藏时关闭旧同意，恢复时重新取得当前政策版本。 */
    function visibility() { if (document.visibilityState === 'hidden') hide(); else restore(); }
    window.addEventListener('pagehide', hide); window.addEventListener('pageshow', restore);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      window.removeEventListener('pagehide', hide); window.removeEventListener('pageshow', restore);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [action.cancel]);
  /** event为实际提交；只发送当前已明确同意的两份政策版本。 */
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!options?.registration.enabled || loading || !accepted.terms || !accepted.privacy) return;
    const passwordLength = Array.from(password).length;
    if (passwordLength < options.password.min_length || passwordLength > options.password.max_length) {
      setValidation(`密码须为 ${options.password.min_length} 至 ${options.password.max_length} 个字符。`); return;
    }
    if (!name.trim() || Array.from(name.trim()).length > 80 || Array.from(email.trim()).length > 254 || Array.from(invite).length > 128) {
      setValidation('请检查填写内容：称呼须为 1 至 80 个字符，邮箱最多 254 个字符，邀请码最多 128 个字符。'); return;
    }
    setValidation('');
    void action.run(signal => register({ email, password, display_name: name, invite_token: invite,
      policy_versions: options.registration.policy_versions }, signal), () => {
      setInvite(''); setName(''); setAccepted({ terms: false, privacy: false }); setCreated(true);
    }, error => {
      if (error.code === 'INVALID_INPUT' || error.code === 'POLICY_VERSION_INVALID' || error.code === 'REGISTRATION_UNAVAILABLE') {
        setAccepted({ terms: false, privacy: false }); setOptions(null); setRevision(value => value + 1);
      }
    }, () => setPassword(''));
  }
  if (created) return <AuthShell registration><div className="registration-success"><CheckCircleIcon size={42} aria-hidden="true" />
    <h2>账号已创建</h2><p>你已完成邀请注册。请使用刚才设置的密码登录。</p>
    <button type="button" className="primary-action" onClick={() => onLogin(email)}>前往登录</button>
  </div></AuthShell>;
  return <AuthShell registration><div className="form-heading"><h2>带着邀请，来这里坐坐。</h2><p>用邀请对应的邮箱，创建你的账号。</p></div>
    {loading && <p role="status" className="loading-note">正在读取注册说明…</p>}
    <ErrorNotice failure={optionFailure} />
    {optionFailure && <button type="button" className="secondary-action" onClick={() => setRevision(value => value + 1)}>重新读取注册说明</button>}
    {options && !options.registration.enabled && <div className="availability-note" role="status">当前暂不开放注册，请稍后再来。<button type="button" className="text-action" onClick={() => setRevision(value => value + 1)}>重新读取注册说明</button></div>}
    <form className="auth-form" onSubmit={submit} aria-busy={action.pending || loading}>
      <div className="auth-field"><label htmlFor="invite">邀请码</label><input id="invite" name="invite_token" type="password" autoComplete="off" required value={invite}
        onChange={event => setInvite(event.target.value)} disabled={action.pending} aria-describedby="invite-help" /><p id="invite-help" className="field-help">邀请码与邮箱绑定，仅可使用一次。</p></div>
      <div className="auth-field"><label htmlFor="display-name">称呼</label><input id="display-name" name="display_name" autoComplete="nickname" required value={name} onChange={event => setName(event.target.value)} disabled={action.pending} /></div>
      <div className="auth-field"><label htmlFor="email">邮箱</label><input id="email" name="email" type="email" autoComplete="username" required value={email} onChange={event => setEmail(event.target.value)} disabled={action.pending} /></div>
      <PasswordField value={password} onChange={setPassword} disabled={action.pending || !options} minLength={options?.password.min_length} maxLength={options?.password.max_length} registering />
      {options && <fieldset className="policy-group" disabled={action.pending || !options.registration.enabled}><legend>请阅读并分别确认</legend>
        {options.registration.policies.map(policy => <div className="policy-document" key={`${policy.kind}:${policy.version}`}>
          <details><summary>{policy.title}</summary><p className="policy-body">{policy.body}</p><p className="policy-version">版本：{policy.version}</p></details>
          {policy.test_only && <p className="field-help">仅适用于本机测试，不是正式上线的法律文件。</p>}
          <label className="consent-label"><input type="checkbox" checked={accepted[policy.kind]} onChange={event => setAccepted(value => ({ ...value, [policy.kind]: event.target.checked }))} />
            <span>我已阅读并同意《{policy.title}》</span></label>
        </div>)}
      </fieldset>}
      <ErrorNotice failure={action.failure} context="register" />
      {validation && <p className="auth-error" role="alert">{validation}</p>}
      <SubmitButton pending={action.pending} seconds={action.seconds} disabled={loading || !options?.registration.enabled || !accepted.terms || !accepted.privacy} label="创建账号" />
    </form>
    <p className="auth-switch">已经有账号？<Link to="/login">返回登录</Link></p>
  </AuthShell>;
}
