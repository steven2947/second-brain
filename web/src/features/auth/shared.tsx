import { characterImage, useCharacter } from '../journal/character';
/** 认证页共用呈现与单次写操作生命周期，不保存浏览器凭据。 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRightIcon, BooksIcon, EyeIcon, EyeSlashIcon, WarningCircleIcon } from '@phosphor-icons/react';
import { ApiFailure } from '../../api/client';

const messages: Record<string, string> = {
  INVALID_CREDENTIALS: '邮箱或密码不匹配，或账号暂不可用。请检查后重新输入密码。',
  AUTH_REQUIRED: '登录状态已失效，请重新登录。',
  MFA_REQUIRED: '管理员需要在独立管理入口完成多因素认证，不能使用普通账号登录。',
  INVITATION_INVALID: '邀请无效、已使用或已过期，请核对邀请对应的邮箱。',
  REGISTRATION_UNAVAILABLE: '当前暂不开放注册，请稍后再试。',
  INVALID_INPUT: '请检查填写内容。注册说明已重新读取，请确认后重新同意。',
  POLICY_VERSION_INVALID: '注册说明已有变化，请阅读最新内容并重新同意。',
  CSRF_FAILED: '请求校验未通过。请重新操作，不会自动重复提交。',
  RATE_LIMITED: '操作过于频繁，请等待后再试。',
  NETWORK_ERROR: '暂时无法连接服务，请检查网络后重试。',
  REQUEST_TIMEOUT: '请求等待超时，请稍后重试。',
  INVALID_RESPONSE: '服务返回了无法识别的结果，请稍后重试。',
};

/** value是捕获异常；只保留受控错误类型，不回显远端自由文本。 */
export function knownFailure(value: unknown): ApiFailure {
  return value instanceof ApiFailure ? value : new ApiFailure('REQUEST_FAILED');
}

/** failure为公开错误，context区分注册说明提示与普通输入校验。 */
export function ErrorNotice({ failure, context }: { failure: ApiFailure | null; context?: 'register' }) {
  if (!failure) return null;
  const message = failure.code === 'INVALID_INPUT' && context !== 'register'
    ? '请检查邮箱和密码的填写内容。'
    : messages[failure.code] ?? '请求暂时未完成，请稍后重试。';
  return <div className="auth-error" role="alert"><WarningCircleIcon size={20} aria-hidden="true" />
    <div><p>{message}</p>{failure.requestId && /^[a-f0-9-]{36}$/i.test(failure.requestId) && <small>请求编号：{failure.requestId}</small>}</div>
  </div>;
}

/** 无参数；管理当前页面单个写请求、重复提交锁和Retry-After等待窗口。 */
export function useWriteAction() {
  const current = useRef<AbortController | null>(null);
  const busy = useRef(false);
  const deadline = useRef(0);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [seconds, setSeconds] = useState(0);
  useEffect(() => () => { current.current?.abort(); busy.current = false; }, []);
  useEffect(() => {
    if (!seconds) return;
    const timer = window.setInterval(() => setSeconds(Math.max(0, Math.ceil((deadline.current - Date.now()) / 1000))), 200);
    return () => window.clearInterval(timer);
  }, [seconds]);
  /** 无参数；失焦/离开时取消当前写结果，不能把取消当作成功。 */
  const cancel = useCallback(() => { current.current?.abort(); busy.current = false; setPending(false); }, []);
  /** operation执行一次真实请求；success/rejected/settled仅在当前请求仍有效时执行。 */
  async function run<T>(operation: (signal: AbortSignal) => Promise<T>, success: (value: T) => void,
    rejected?: (error: ApiFailure) => void, settled?: () => void) {
    if (busy.current || Date.now() < deadline.current) return;
    busy.current = true;
    const controller = new AbortController();
    current.current = controller;
    setPending(true); setFailure(null);
    try {
      const value = await operation(controller.signal);
      if (!controller.signal.aborted) { settled?.(); success(value); }
    } catch (error) {
      if (!controller.signal.aborted) {
        const safe = knownFailure(error);
        setFailure(safe);
        if (safe.status === 429) {
          const wait = Math.max(1, safe.retryAfter ?? 30);
          deadline.current = Date.now() + wait * 1000;
          setSeconds(wait);
        }
        settled?.(); rejected?.(safe);
      }
    } finally {
      if (!controller.signal.aborted) { busy.current = false; setPending(false); }
    }
  }
  return { pending, failure, seconds, run, cancel };
}

/** value/onChange是仅驻留当前表单的密码；limits来自已验证的服务端规则。 */
export function PasswordField({ value, onChange, disabled, minLength, maxLength = 256, registering = false }: {
  value: string; onChange: (value: string) => void; disabled?: boolean; minLength?: number; maxLength?: number; registering?: boolean;
}) {
  const [visible, setVisible] = useState(false);
  useEffect(() => { if (!value) setVisible(false); }, [value]);
  return <div className="auth-field"><label htmlFor="password">密码</label>
    <div className="password-control"><input id="password" name="password" type={visible ? 'text' : 'password'} value={value}
      onChange={event => onChange(event.target.value)} required
      disabled={disabled} autoComplete={registering ? 'new-password' : 'current-password'} aria-describedby={registering ? 'password-help' : undefined} />
      <button className="password-toggle" type="button" onClick={() => setVisible(value => !value)} aria-label={visible ? '隐藏密码' : '显示密码'} aria-pressed={visible}>
        {visible ? <EyeSlashIcon size={20} aria-hidden="true" /> : <EyeIcon size={20} aria-hidden="true" />}
      </button>
    </div>
    {registering && minLength && <p className="field-help" id="password-help">{minLength} 至 {maxLength} 个字符。请避免常见密码、纯数字和与个人信息相近的内容。</p>}
  </div>;
}

/** children为当前公开页面表单；registration选择紧凑标题以容纳真实政策正文。 */
export function AuthShell({ children, registration = false }: { children: ReactNode; registration?: boolean }) {
  const [character] = useCharacter();
  return <div className={`product-shell ${registration ? 'registration-shell' : ''}`}>
    <a className="skip-link" href="#main-content">跳转到主要内容</a>
    <header className="product-header"><Link to="/" className="product-brand" aria-label="第二大脑首页"><BooksIcon size={27} weight="regular" aria-hidden="true" /><span>第二大脑</span></Link>
      <span className="header-note">让读过的书，走进生活</span>
    </header>
    <main id="main-content" className="auth-layout">
      <section className="library-intro" aria-labelledby="library-heading"><div className="library-copy">
        <h1 id="library-heading">把书中智慧，<br />带回真实问题。</h1>
        <p>为每一次思考，留一个可以追溯的起点。</p>
      </div>
        <figure className="journal-collage" aria-hidden="true">
          <span className="journal-tape" />
          <img className="collage-photo" src="/journal/hero-desk.png" alt="" />
          <img className="collage-sticker" src={characterImage("/journal/librarian-reading", character)} alt="" />
          <figcaption className="hand-note">馆员的小书桌 · 每天都在</figcaption>
        </figure>
      </section>
      <section className="auth-form-panel" aria-label={registration ? '邀请注册' : '账号登录'}>{children}</section>
    </main>
    <footer className="product-footer"><span>第二大脑</span><span>提问、答案、知识库与学习练习，都已接入。</span></footer>
  </div>;
}

/** pending/seconds对应实际请求与服务端等待；label为当前动作名称。 */
export function SubmitButton({ pending, seconds, disabled, label }: { pending: boolean; seconds: number; disabled?: boolean; label: string }) {
  return <button className="primary-action" type="submit" disabled={pending || seconds > 0 || disabled}>
    {pending ? '正在提交…' : seconds > 0 ? `${seconds} 秒后可重试` : label}<ArrowRightIcon size={19} aria-hidden="true" />
  </button>;
}
