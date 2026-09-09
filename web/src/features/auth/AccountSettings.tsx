/** 账号设置子表单仅在当前身份已核验时挂载；父页隐藏会卸载全部敏感草稿。 */
import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type { PublicUser } from '../../api/auth';
import { ApiFailure } from '../../api/client';
import { changePassword, logoutAll, saveProfile } from '../../api/account-settings';
import { readRecoveryOptions } from '../../api/recovery';
import { ErrorNotice, knownFailure, SubmitButton, useWriteAction } from './shared';
type Reject = (failure: ApiFailure) => void;
/** failure为密码重验错误；不将INVALID_CREDENTIALS误当会话过期。 */
function SettingsError({ failure }: { failure: ApiFailure | null }) { return failure?.code === 'INVALID_CREDENTIALS' ? <p className="auth-error" role="alert">当前密码验证未通过，请重新输入。</p> : <ErrorNotice failure={failure} />; }
/** user/update来自当前身份，reject由父页统一处理真正的AUTH_REQUIRED。 */
function ProfileForm({ user, update, reject }: { user: PublicUser; update: (user: PublicUser) => void; reject: Reject }) {
  const [name, setName] = useState(user.display_name), [saved, setSaved] = useState(false), write = useWriteAction();
  /** event为显式修改，仅传本次称呼，不覆盖其他设置。 */
  function submit(event: FormEvent) { event.preventDefault(); if (!name.trim()) return; setSaved(false); void write.run(signal => saveProfile(user.id, { display_name: name }, signal), value => { setName(value.display_name); update(value); setSaved(true); }, reject); }
  return <section className="account-details"><h2>修改资料</h2><p>邮箱暂不支持在此修改。</p><form className="auth-form" onSubmit={submit}><div className="auth-field"><label htmlFor="profile-name">修改称呼</label><input id="profile-name" value={name} maxLength={80} required disabled={write.pending} onChange={event => { setName(event.target.value); setSaved(false); }} /></div><SettingsError failure={write.failure} /><SubmitButton label="保存称呼" pending={write.pending} seconds={write.seconds} disabled={!name.trim()} /></form>{saved && <p role="status">称呼已保存。</p>}</section>;
}
/** reject处理真实会话失效，密码规则读取现有匿名能力，不依赖邮件可用。 */
function PasswordForm({ reject }: { reject: Reject }) {
  const [current, setCurrent] = useState(''), [next, setNext] = useState(''), [confirmation, setConfirmation] = useState(''), [notice, setNotice] = useState(''), [validation, setValidation] = useState('');
  const [limits, setLimits] = useState<{ min_length: number; max_length: number } | null>(null), [failure, setFailure] = useState<ApiFailure | null>(null), [revision, setRevision] = useState(0), write = useWriteAction();
  useEffect(() => { const request = new AbortController(); setFailure(null); readRecoveryOptions(request.signal).then(value => { if (!request.signal.aborted) setLimits(value.password); }).catch(error => { if (!request.signal.aborted) setFailure(knownFailure(error)); }); return () => request.abort(); }, [revision]);
  /** event为明确改密；校验两次一致，所有完成响应均清空密码。 */
  function submit(event: FormEvent) { event.preventDefault(); if (!limits) return; setNotice(''); if (next !== confirmation) { setValidation('两次输入的新密码不一致。'); return; } const size = Array.from(next).length; if (size < limits.min_length || size > limits.max_length) { setValidation(`新密码须为 ${limits.min_length} 至 ${limits.max_length} 个字符。`); return; } setValidation(''); void write.run(signal => changePassword({ current_password: current, new_password: next }, signal), () => setNotice('密码已更新，当前会话保留；其他旧会话已失效。'), reject, () => { setCurrent(''); setNext(''); setConfirmation(''); }); }
  return <section className="account-details"><h2>修改密码</h2>{limits && <p>{limits.min_length} 至 {limits.max_length} 个字符，避免常见密码和个人信息。</p>}{failure && <><SettingsError failure={failure} /><button type="button" onClick={() => setRevision(value => value + 1)}>重新读取密码要求</button></>}
    <form className="auth-form" onSubmit={submit}>{[{ id: 'current-password', label: '当前密码', value: current, set: setCurrent, auto: 'current-password' }, { id: 'new-password', label: '新密码', value: next, set: setNext, auto: 'new-password' }, { id: 'confirm-new-password', label: '再次输入新密码', value: confirmation, set: setConfirmation, auto: 'new-password' }].map(field => <div className="auth-field" key={field.id}><label htmlFor={field.id}>{field.label}</label><input id={field.id} type="password" autoComplete={field.auto} maxLength={256} required value={field.value} onChange={event => { field.set(event.target.value); setNotice(''); }} disabled={write.pending} /></div>)}{validation && <p className="auth-error" role="alert">{validation}</p>}<SettingsError failure={write.failure} /><SubmitButton label="更新密码" pending={write.pending} seconds={write.seconds} disabled={!limits || !current || !next || !confirmation} /></form>{notice && <p role="status">{notice}</p>}
  </section>;
}
/** reject与leave由身份父页提供；只有真实204才触发离开。 */
function LogoutAllForm({ reject, leave }: { reject: Reject; leave: () => void }) {
  const [password, setPassword] = useState(''), [confirmed, setConfirmed] = useState(false), write = useWriteAction();
  /** event为本人明确全退出，不在页面打开时自动撤销会话。 */
  function submit(event: FormEvent) { event.preventDefault(); if (!confirmed || !password) return; void write.run(signal => logoutAll(password, signal), leave, reject, () => setPassword('')); }
  return <section className="account-details"><h2>退出全部设备</h2><p>如果怀疑账号在其他设备登录，可撤销全部旧会话。此操作不删除个人记录。</p><form className="auth-form" onSubmit={submit}><div className="auth-field"><label htmlFor="logout-all-password">全退出验证密码</label><input id="logout-all-password" type="password" autoComplete="current-password" maxLength={256} required value={password} onChange={event => setPassword(event.target.value)} disabled={write.pending} /></div><label><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} disabled={write.pending} />我理解包括当前设备也会退出，需要重新登录</label><SettingsError failure={write.failure} /><SubmitButton label="退出所有设备" pending={write.pending} seconds={write.seconds} disabled={!confirmed || !password} /></form></section>;
}
/** user/update/reject/leave均来自同一身份父页，不自行读取其他账号。 */
export function AccountSettings({ user, update, reject, leave }: { user: PublicUser; update: (user: PublicUser) => void; reject: Reject; leave: () => void }) { return <><ProfileForm user={user} update={update} reject={reject} /><PasswordForm reject={reject} /><LogoutAllForm reject={reject} leave={leave} /></>; }
