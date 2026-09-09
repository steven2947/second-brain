import { AppHeader } from '../journal/Chrome';
/** 独立学习入口：登录通过后才读取学习资料，页面隐藏时清理全部私有状态。 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { readMe } from '../../api/auth';
import { ApiFailure } from '../../api/client';
import { knownFailure } from '../auth/shared';
import { LearningCatalog, LearningCreate } from './LearningViews';
import { LearningRoom } from './LearningRoom';
import '../../styles/library.css';
import '../../styles/learning.css';

const Failure = createContext<(error: ApiFailure) => void>(() => {});
/** 无参数；下级读取或写入失权时卸载整个学习内容。 */
export function useLearningFailure() { return useContext(Failure); }
/** create选择创建页面；id从受保护路由取得，不携带正文或个人草稿。 */
export function LearningPage({ create = false }: { create?: boolean }) {
  const { id } = useParams(), navigate = useNavigate(), identity = useRef<AbortController | null>(null);
  const [ready, setReady] = useState(false), [failure, setFailure] = useState<ApiFailure | null>(null), [retry, setRetry] = useState(0);
  const fail = useCallback((error: ApiFailure) => { identity.current?.abort(); setReady(false); setFailure(error); if (error.status === 401) navigate('/login', { replace: true }); }, [navigate]);
  useEffect(() => {
    let suspended = document.visibilityState === 'hidden';
    /** 无参数；不接受旧账号请求在新身份下挂载结果。 */
    function verify() { if (document.visibilityState === 'hidden') return; suspended = false; identity.current?.abort(); const request = new AbortController(); identity.current = request; setReady(false); setFailure(null); readMe(request.signal).then(() => { if (!request.signal.aborted) setReady(true); }).catch(error => { if (!request.signal.aborted) fail(knownFailure(error)); }); }
    /** 无参数；同步销毁学习正文、练习回答与所有未返回请求。 */
    function hide() { suspended = true; identity.current?.abort(); flushSync(() => { setReady(false); setFailure(null); }); }
    /** 无参数；恢复时必须重新确认会话与知识许可。 */
    function restore() { if (suspended) verify(); }
    /** 无参数；处理浏览器标签可见性。 */
    function visibility() { if (document.visibilityState === 'hidden') hide(); else restore(); }
    if (!suspended) verify();
    window.addEventListener('pagehide', hide); window.addEventListener('pageshow', restore); document.addEventListener('visibilitychange', visibility);
    return () => { identity.current?.abort(); window.removeEventListener('pagehide', hide); window.removeEventListener('pageshow', restore); document.removeEventListener('visibilitychange', visibility); };
  }, [fail, retry]);
  return <div className="product-shell reading-shell"><a className="skip-link" href="#main-content">跳转到主要内容</a>
    <AppHeader />
    <main id="main-content" className="reading-main learning-main">
      {failure ? <section className="reading-empty"><h1>暂时无法打开学习记录</h1><p role="alert">{failure.status === 404 ? '记录不存在或当前知识授权不可用。' : '连接暂未完成，请稍后重新读取。'}</p><button type="button" onClick={() => setRetry(value => value + 1)}>重新读取</button><Link to="/app/learning">返回学习列表</Link></section>
        : !ready ? <p role="status">正在确认登录状态…</p>
          : <Failure.Provider value={fail}>{create ? <LearningCreate /> : id ? <LearningRoom key={id} id={id} /> : <LearningCatalog />}</Failure.Provider>}
    </main><footer className="product-footer"><span>第二大脑 · 学习室</span><span>理解原理，再用自己的回答检验理解。</span></footer>
  </div>;
}

/** error为受控请求错误，不直接显示服务端自由文本或内部错误堆栈。 */
export function LearningError({ error }: { error: ApiFailure | null }) {
  if (!error) return null;
  return <p role="alert" className="learning-error">{error.status === 409 ? '记录已有变化。你的输入仍在，请重新读取最新记录后再提交。' : error.status === 429 ? '当前额度或请求频率受限，请等待后再试。' : error.code === 'MODEL_UNAVAILABLE' ? '尚未配置可用模型，本次没有生成学习内容。' : error.status === 400 ? '请检查目标、选卡或回答所对应的练习。' : '请求尚未确认完成。请先重读记录；同一内容重试会沿用原提交凭据。'}</p>;
}
