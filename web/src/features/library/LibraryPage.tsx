import { AppHeader } from '../journal/Chrome';
/** 只读知识库入口；身份边界卸载整个私有子树，读取失败不保留旧标题。 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { ArrowClockwiseIcon } from '@phosphor-icons/react';
import { readMe } from '../../api/auth';
import { ApiFailure } from '../../api/client';
import { LibraryCatalog, BookReader, CardReader } from './LibraryViews';
import '../../styles/library.css';

const FailureContext = createContext<(error: unknown) => void>(() => {});
/** 无参数；写操作失权时复用阅读边界，卸载旧知识内容。 */
export function useLibraryFailure() { return useContext(FailureContext); }
/** load为当前已获准视图的稳定读取函数；卸载/更换时取消，只接受本次结果。 */
export function useLibraryRead<T>(load: (signal: AbortSignal) => Promise<T>): T | null {
  const [result, setResult] = useState<{ load: typeof load; value: T } | null>(null);
  const fail = useContext(FailureContext);
  useEffect(() => {
    const request = new AbortController();
    load(request.signal).then(value => { if (!request.signal.aborted) setResult({ load, value }); })
      .catch(error => { if (!request.signal.aborted) fail(error); });
    return () => request.abort();
  }, [load, fail]);
  return result?.load === load ? result.value : null;
}
/** 无参数；为读取中的当前位置提供明确且可访问的反馈。 */
export function ReadingStatus() { return <p className="reading-status" role="status">正在读取知识内容…</p>; }
/** value为URL公开ID，禁止路径或控制字符；不输出非法输入本身。 */
function validId(value: string | undefined) { return !!value && value.length <= 240 && !/[\s/\\?#\u0000-\u001f]/u.test(value) && value !== '.' && value !== '..'; }
/** 无参数；每次进入、恢复或手动刷新都先确认会话，再挂载私有读取与表单。 */
export function LibraryPage() {
  const params = useParams(), location = useLocation(), navigate = useNavigate();
  const requestedRelease = new URLSearchParams(location.search).get('release') ?? undefined;
  const release = params.release ?? requestedRelease;
  const valid = (!release || /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(release))
    && (!params.book || validId(params.book)) && (!params.card || validId(params.card));
  const [ready, setReady] = useState(false), [failure, setFailure] = useState<ApiFailure | null>(null);
  const [revision, setRevision] = useState(0);
  const identity = useRef<AbortController | null>(null);
  const fail = useCallback((error: unknown) => {
    const safe = error instanceof ApiFailure ? error : new ApiFailure('REQUEST_FAILED');
    identity.current?.abort(); setReady(false); setFailure(safe);
    if (safe.status === 401) navigate('/login', { replace: true });
  }, [navigate]);
  useEffect(() => {
    let suspended = document.visibilityState === 'hidden';
    /** 无参数；会话成功前不发知识请求，过期身份响应不会重新挂载私有内容。 */
    function verify() {
      if (document.visibilityState === 'hidden') return;
      suspended = false;
      identity.current?.abort();
      const request = new AbortController(); identity.current = request;
      setReady(false); setFailure(null);
      readMe(request.signal).then(() => { if (!request.signal.aborted) setReady(true); })
        .catch(error => { if (!request.signal.aborted) fail(error); });
    }
    /** 无参数；同步卸载，清掉表单/证据及所有分页结果，并执行子树请求清理。 */
    function hide() { suspended = true; identity.current?.abort(); flushSync(() => { setReady(false); setFailure(null); }); }
    /** 无参数；合并紧邻的pageshow/visible恢复事件，避免重复加载。 */
    function restore() { if (suspended) verify(); }
    /** 无参数；页面不可见时销毁全部私有状态。 */
    function visibility() { if (document.visibilityState === 'hidden') hide(); else restore(); }
    if (!suspended) verify();
    window.addEventListener('pagehide', hide); window.addEventListener('pageshow', restore);
    document.addEventListener('visibilitychange', visibility);
    return () => { identity.current?.abort(); window.removeEventListener('pagehide', hide); window.removeEventListener('pageshow', restore); document.removeEventListener('visibilitychange', visibility); };
  }, [fail, revision]);
  const message = failure?.status === 404 ? '内容不存在或当前不可访问' : failure?.code === 'RELEASE_UNAVAILABLE'
    ? '此知识版本暂时不可用' : failure?.status === 400 ? '查询条件无效，请返回知识库重新查询' : '暂时无法读取知识内容，请稍后重试';
  return <div className="product-shell reading-shell"><a className="skip-link" href="#main-content">跳转到主要内容</a>
    <AppHeader />
    <main id="main-content" className="reading-main">
      {!valid ? <section className="reading-empty"><h1>地址参数无效</h1><Link to="/app/library">返回知识库</Link></section>
        : failure ? <section className="reading-empty"><h1>暂时无法阅读</h1><p role="alert">{message}</p><button onClick={() => setRevision(value => value + 1)} type="button"><ArrowClockwiseIcon size={18} aria-hidden="true" />重新读取</button><Link className="link-action" to="/app/library">返回知识库</Link></section>
          : !ready ? <p className="reading-status" role="status">正在确认登录状态…</p>
            : <FailureContext.Provider value={fail}><div className="reading-tools"><span>只读知识库</span><button className="text-action" type="button" onClick={() => { setReady(false); setRevision(value => value + 1); }}><ArrowClockwiseIcon size={17} aria-hidden="true" />重新读取</button></div>
              {params.card && release ? <CardReader release={release} id={params.card} /> : params.book && release ? <BookReader release={release} id={params.book} /> : <LibraryCatalog initialRelease={release} />}
            </FailureContext.Provider>}
    </main><footer className="product-footer"><span>第二大脑</span><span>以真实来源，支持每一次思考。</span></footer>
  </div>;
}
