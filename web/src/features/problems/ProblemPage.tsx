import { AppHeader } from '../journal/Chrome';
/** 问题页身份边界；会话验证前不挂载私有读取与草稿，离开时销毁内存。 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { ArrowClockwiseIcon } from '@phosphor-icons/react';
import { readMe } from '../../api/auth';
import { ApiFailure } from '../../api/client';
import { ProblemCatalog, ProblemCreate, ProblemDetail } from './ProblemViews';
import '../../styles/library.css';
import '../../styles/problems.css';

const FailureContext = createContext<(error: unknown) => void>(() => {});
/** 无参数；返回身份边界错误处理，401/404可直接销毁全部私有子树。 */
export function useProblemFailure() { return useContext(FailureContext); }
/** load为稳定的分页读取函数；更换查询立即遮蔽旧页，只接受未取消结果。 */
export function useProblemRead<T>(load: (signal: AbortSignal) => Promise<T>): T | null {
  const [result, setResult] = useState<{ load: typeof load; value: T } | null>(null);
  const fail = useProblemFailure();
  useEffect(() => {
    const request = new AbortController();
    load(request.signal).then(value => { if (!request.signal.aborted) setResult({ load, value }); })
      .catch(error => { if (!request.signal.aborted) fail(error); });
    return () => request.abort();
  }, [load, fail]);
  return result?.load === load ? result.value : null;
}
/** 无参数；每次进入与恢复页面均重新确认身份，旧账号内容不会参与下一次渲染。 */
export function ProblemPage({ reviewDraft, onReviewUsed }: { reviewDraft?: { problemId: string; prompt: string } | null; onReviewUsed?: () => void } = {}) {
  const { id } = useParams(), location = useLocation(), navigate = useNavigate();
  const [ready, setReady] = useState(false), [failure, setFailure] = useState<ApiFailure | null>(null);
  const [attempt, setAttempt] = useState(0);
  const identity = useRef<AbortController | null>(null);
  const valid = !id || /^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(id);
  const fail = useCallback((error: unknown) => {
    const safe = error instanceof ApiFailure ? error : new ApiFailure('REQUEST_FAILED');
    identity.current?.abort(); setReady(false); setFailure(safe);
    if (safe.status === 401) navigate('/login', { replace: true });
  }, [navigate]);
  useEffect(() => {
    let suspended = document.visibilityState === 'hidden';
    /** 无参数；恢复先验证会话，隐藏期间不发请求。 */
    function verify() {
      if (document.visibilityState === 'hidden') return;
      suspended = false; identity.current?.abort();
      const request = new AbortController(); identity.current = request;
      setReady(false); setFailure(null);
      readMe(request.signal).then(() => { if (!request.signal.aborted) setReady(true); })
        .catch(error => { if (!request.signal.aborted) fail(error); });
    }
    /** 无参数；同步卸载私有子树，执行读写请求及草稿清理。 */
    function hide() { suspended = true; identity.current?.abort(); flushSync(() => { setReady(false); setFailure(null); }); }
    /** 无参数；合并同一次pageshow/visible恢复，避免重复验证。 */
    function restore() { if (suspended) verify(); }
    /** 无参数；标签隐藏即清理，恢复后重新确认身份。 */
    function visibility() { if (document.visibilityState === 'hidden') hide(); else restore(); }
    if (!suspended) verify();
    window.addEventListener('pagehide', hide); window.addEventListener('pageshow', restore); document.addEventListener('visibilitychange', visibility);
    return () => { identity.current?.abort(); window.removeEventListener('pagehide', hide); window.removeEventListener('pageshow', restore); document.removeEventListener('visibilitychange', visibility); };
  }, [fail, attempt]);
  return <div className="product-shell reading-shell problem-shell"><a className="skip-link" href="#main-content">跳转到主要内容</a>
    <AppHeader />
    <main id="main-content" className="reading-main">
      {!valid ? <section className="reading-empty"><h1>问题不存在或当前不可访问</h1><Link to="/app/problems">返回我的问题</Link></section>
        : failure ? <section className="reading-empty"><h1>暂时无法打开问题</h1><p role="alert">{failure.status === 404 ? '问题不存在或当前不可访问' : '暂时无法读取，请稍后重试'}</p><button type="button" onClick={() => setAttempt(value => value + 1)}><ArrowClockwiseIcon size={18} aria-hidden="true" />重新读取</button><Link className="link-action" to="/app/problems">返回我的问题</Link></section>
          : !ready ? <p className="reading-status" role="status">正在确认登录状态…</p>
            : <FailureContext.Provider value={fail}>{id ? <ProblemDetail key={id} id={id} initialDraft={reviewDraft?.problemId === id ? reviewDraft.prompt : undefined} onDraftUsed={onReviewUsed} /> : location.pathname.endsWith('/new') ? <ProblemCreate /> : <ProblemCatalog />}</FailureContext.Provider>}
    </main><footer className="product-footer"><span>第二大脑</span><span>以真实来源，支持每一次思考。</span></footer>
  </div>;
}
