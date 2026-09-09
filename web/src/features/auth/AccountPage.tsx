/** 已登录账号入口；私有信息只驻留当前视图，每次恢复页面重新校验会话。提问优先：家页即工作台。 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { Link, useNavigate } from 'react-router-dom';
import { BooksIcon, SignOutIcon, ArrowClockwiseIcon, ArrowRightIcon } from '@phosphor-icons/react';
import { logout, readMe } from '../../api/auth';
import type { PublicUser } from '../../api/auth';
import { ApiFailure } from '../../api/client';
import { ErrorNotice, knownFailure, useWriteAction } from './shared';
import { AccountSettings } from './AccountSettings';
import { CharacterSwitch } from '../journal/Switch';
import { characterImage, useCharacter } from '../journal/character';
import { readLibraries } from '../../api/knowledge';
import type { LibraryPage } from '../../api/knowledge';
import { createProblem, readProblems } from '../../api/problems';
import type { Problem } from '../../api/problems';
import { sendMessage } from '../../api/runs';

const goals: Record<Problem['goal'], string> = { explain: '理解一个概念', analyze: '分析一个问题', compare: '比较不同选择', act: '制定行动计划', review: '复盘一次经历' };

/** releases为获准知识集；一次提交=创建问题+发出首条消息，随后进入对话页开始澄清。 */
function AskComposer({ releases, onCreated }: { releases: LibraryPage | null; onCreated: (id: string) => void }) {
  const [draft, setDraft] = useState('');
  const [goal, setGoal] = useState<Problem['goal']>('analyze');
  const [release, setRelease] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiFailure | null>(null);
  const submitted = useRef<{ signature: string; problemKey: string; messageKey: string; clientId: string } | null>(null);
  const count = Array.from(draft).length;
  const releaseId = release || releases?.items[0]?.id || '';
  const ready = !!releaseId && !!draft.trim() && count <= 4000 && !busy;

  async function start() {
    if (!ready) return;
    const text = draft.trim();
    const signature = JSON.stringify({ text, goal, releaseId });
    if (submitted.current?.signature !== signature) {
      submitted.current = { signature, problemKey: crypto.randomUUID(), messageKey: crypto.randomUUID(), clientId: crypto.randomUUID() };
    }
    const keys = submitted.current;
    setBusy(true); setError(null);
    try {
      const created = await createProblem({ question: text, goal, release_id: releaseId }, keys.problemKey);
      await sendMessage(created.id, { content: text, intent: 'unknown', client_message_id: keys.clientId, expected_revision: created.revision }, keys.messageKey);
      onCreated(created.id);
    } catch (error) {
      const safe = error instanceof ApiFailure ? error : new ApiFailure('REQUEST_FAILED');
      setError(safe);
    } finally {
      setBusy(false);
    }
  }
  const hasReleases = (releases?.items.length ?? 0) > 0;
  return <section className="home-ask note-card" aria-label="向书房提问">
    <span className="journal-tape tape-stripe" aria-hidden="true"></span>
    <label className="section-label" htmlFor="home-ask-input">有问题，现在就问</label>
    <textarea id="home-ask-input" value={draft} rows={4} maxLength={4000} disabled={busy || !hasReleases}
      onChange={event => setDraft(event.target.value)}
      onKeyDown={event => { if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') void start(); }}
      placeholder="写下你此刻真实的困惑，越具体越好……&#10;例如：我下班后总想刷手机，学习计划总坚持不过三天，怎么建立可持续的学习习惯？" />
    <div className="home-ask-row">
      <div className="home-ask-field"><label htmlFor="home-ask-goal">这次想</label>
        <select id="home-ask-goal" value={goal} disabled={busy} onChange={event => setGoal(event.target.value as Problem['goal'])}>
          {Object.entries(goals).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></div>
      <div className="home-ask-field"><label htmlFor="home-ask-release">用哪间书房</label>
        <select id="home-ask-release" value={releaseId} disabled={busy || !hasReleases} onChange={event => setRelease(event.target.value)}>
          {hasReleases ? releases!.items.map(item => <option key={item.id} value={item.id}>{item.title} · {item.book_count} 本书</option>) : <option>暂无获准知识集</option>}
        </select></div>
      <button type="button" className="home-ask-go" disabled={busy || !draft.trim()} onClick={() => void start()}>
        {busy ? '正在提交…' : '开始提问'}<ArrowRightIcon size={18} aria-hidden="true" />
      </button>
    </div>
    <p className="reading-muted">提交后 AI 会先问你两三个澄清问题，再给出带书里出处的答案。⌘/Ctrl + Enter 直接提交。{count > 0 ? ` ${count} / 4000 字符。` : ''}</p>
    {!hasReleases && <p className="reading-muted">还没有可用的知识集——先去书房看看，或联系管理员授权。</p>}
    {error && <div className="problem-notice" role="alert"><p>{error.status === 409 ? '问题已更新，请重试。' : error.status === 429 ? '操作过于频繁，请稍后再试。' : '提交未完成，草稿已保留，请重试。'}</p>{error.requestId && <small>请求编号：{error.requestId}</small>}</div>}
  </section>;
}

/** 避免与家页自身的失败边界耦合；composer内部消化读取错误。 */

/** 问题为本人档案；读取失败静默为空，不影响主流程。 */
function RecentProblems() {
  const [problems, setProblems] = useState<Problem[] | null>(null);
  useEffect(() => {
    const request = new AbortController();
    readProblems({ status: 'active' }, request.signal)
      .then(page => { if (!request.signal.aborted) setProblems(page.items.slice(0, 5)); })
      .catch(() => { if (!request.signal.aborted) setProblems([]); });
    return () => request.abort();
  }, []);
  if (!problems?.length) return null;
  return <section className="home-recent" aria-label="最近的问题">
    <p className="section-label">最近在想</p>
    <ul className="problem-list">{problems.map(problem => <li key={problem.id}><div><h2><Link to={`/app/problems/${problem.id}`}>{problem.title}</Link></h2><p>{goals[problem.goal]} · 进行中 · 修订 {problem.revision}</p></div><ArrowRightIcon size={20} aria-hidden="true" /></li>)}</ul>
  </section>;
}

/** settings选择账号设置；仅在真实readMe成功后显示账号和对应操作。 */
export function AccountPage({ settings = false }: { settings?: boolean }) {
  const [user, setUser] = useState<PublicUser | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [libraries, setLibraries] = useState<LibraryPage | null>(null);
  const [character] = useCharacter();
  const controller = useRef<AbortController | null>(null);
  const action = useWriteAction();
  const navigate = useNavigate();
  const rejectSettings = useCallback((error: ApiFailure) => { if (error.code === 'AUTH_REQUIRED') { setUser(null); navigate('/login', { replace: true }); } }, [navigate]);
  useEffect(() => {
    /** 无参数；只接受最近一次会话读取结果。 */
    function verify() {
      controller.current?.abort();
      const request = new AbortController(); controller.current = request;
      setUser(null); setLoading(true); setFailure(null);
      readMe(request.signal).then(value => { if (!request.signal.aborted) setUser(value); })
        .catch(error => {
          if (request.signal.aborted) return;
          const safe = knownFailure(error);
          if (safe.status === 401) navigate('/login', { replace: true });
          else setFailure(safe);
        }).finally(() => { if (!request.signal.aborted) setLoading(false); });
    }
    /** 无参数；同步清空私有DOM，避免浏览器恢复缓存画面显示旧资料。 */
    function hide() {
      controller.current?.abort(); action.cancel();
      flushSync(() => { setUser(null); setLoading(true); setFailure(null); });
    }
    /** 无参数；切回标签页时必须重新读取，切走时立即遮蔽。 */
    function visibility() { if (document.visibilityState === 'hidden') hide(); else verify(); }
    verify();
    window.addEventListener('pagehide', hide); window.addEventListener('pageshow', verify);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      controller.current?.abort(); window.removeEventListener('pagehide', hide); window.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('pagehide', hide); window.removeEventListener('pageshow', verify);
    };
  }, [navigate, revision, action.cancel]);
  /** 获准知识集跟随会话读取一次；读取失败按空处理，不阻塞账号信息。 */
  useEffect(() => {
    if (!user || settings) return;
    const request = new AbortController();
    readLibraries({}, request.signal).then(value => { if (!request.signal.aborted) setLibraries(value); }).catch(() => { if (!request.signal.aborted) setLibraries({ items: [], next_cursor: null }); });
    return () => request.abort();
  }, [user, settings]);
  /** 无参数；退出只有服务端204确认后才导航，不把失败显示为成功。 */
  function leave() { void action.run(signal => logout(signal), () => { setUser(null); navigate('/login', { replace: true }); }); }
  return <div className="product-shell account-shell"><a className="skip-link" href="#main-content">跳转到主要内容</a>
    <AppHeader />
    <main id="main-content" className="account-content">
      {loading ? <section className="account-loading" role="status"><div className="loading-line" /><div className="loading-line short" /><p>正在确认登录状态…</p></section>
        : failure ? <section><h1>暂时无法读取账号</h1><ErrorNotice failure={failure} /><button type="button" onClick={() => setRevision(value => value + 1)}><ArrowClockwiseIcon size={18} aria-hidden="true" />重新读取账号</button></section>
          : user && (settings ? <>
            <section className="account-details" aria-label="账号资料"><dl><div><dt>邮箱</dt><dd>{user.email}</dd><dd className="verification-note">{user.email_verified_at ? '邮箱已验证' : '邮箱尚未验证'}</dd></div><div><dt>称呼</dt><dd>{user.display_name || '尚未填写'}</dd></div></dl>
              <ErrorNotice failure={action.failure} /><button className="secondary-action" type="button" onClick={leave} disabled={action.pending || action.seconds > 0}><SignOutIcon size={19} aria-hidden="true" />{action.pending ? '正在退出…' : action.seconds > 0 ? `${action.seconds} 秒后可重试` : '退出登录'}</button>
            </section>
            {settings && <AccountSettings user={user} update={setUser} reject={rejectSettings} leave={() => { setUser(null); navigate('/login', { replace: true }); }} />}
            <p className="account-back-row"><Link to="/app">返回账号首页</Link></p>
          </> : <>
            <section className="home-hero-row">
              <div className="home-hero-copy">
                <p className="section-label">{new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}</p>
                <h1>你好，{user.display_name || '读者'}</h1>
                <p className="home-hero-sub">有问题就想起来问一句——用完就走，书里的方法会留在你的记录里。</p>
              </div>
              <img className="home-welcome-reader" src={characterImage('/journal/librarian-reading', character)} alt="" aria-hidden="true" />
            </section>
            <AskComposer releases={libraries} onCreated={id => navigate(`/app/problems/${id}`)} />
            <RecentProblems />
            <section className="account-strip" aria-label="账号资料">
              <div className="account-strip-info"><span>{user.email}</span><small>{user.email_verified_at ? '邮箱已验证' : '邮箱尚未验证'}</small><small>称呼 {user.display_name || '尚未填写'}</small></div>
              <div className="account-strip-actions">
                <ErrorNotice failure={action.failure} />
                <CharacterSwitch />
                <Link className="text-action" to="/app/settings">账号设置与安全</Link>
                <button className="secondary-action" type="button" onClick={leave} disabled={action.pending || action.seconds > 0}><SignOutIcon size={19} aria-hidden="true" />退出登录</button>
              </div>
            </section>
            <p className="home-links"><Link to="/app/library">进入知识库</Link> · <Link to="/app/learning">我的学习</Link> · <Link to="/app/bookmarks">我的收藏</Link> · <Link to="/app/actions">我的行动</Link> · <Link to="/app/privacy">隐私与数据导出</Link> · <Link to="/app/trash">问题回收站</Link></p>
          </>)}
    </main><footer className="product-footer"><span>第二大脑</span><span>以真实来源，支持每一次思考。</span></footer>
  </div>;
}

/** 家页自己的AppHeader包装：当前页始终是"我的账号"。 */
function AppHeader() {
  return <header className="product-header"><Link to="/app" className="product-brand"><BooksIcon size={27} aria-hidden="true" />第二大脑</Link>
    <nav aria-label="主导航"><Link to="/app/library">书房</Link><Link to="/app/problems">我的问题</Link><Link to="/app/learning">我的学习</Link><Link to="/app/bookmarks">我的收藏</Link><Link to="/app/actions">我的行动</Link></nav><span className="header-note">我的账号</span></header>;
}
