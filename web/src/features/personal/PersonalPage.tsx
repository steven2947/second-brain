import { PageHero } from '../journal/Chrome';
import { AppHeader } from '../journal/Chrome';
/** 个人实践页：身份验证后读取收藏与行动，隐藏页面立即卸载私有状态。 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { Link, useNavigate } from 'react-router-dom';
import { readMe } from '../../api/auth';
import { ApiFailure } from '../../api/client';
import { readActions, readBookmarks, removeBookmark, saveBookmark, updateAction } from '../../api/personal';
import type { ActionRecord, ActionStatus, Bookmark } from '../../api/personal';
import { knownFailure, useWriteAction } from '../auth/shared';
import { PersonalError } from './PersonalControls';
import '../../styles/library.css';
import '../../styles/personal.css';

const Failure = createContext<(error: ApiFailure) => void>(() => {});
const statusLabels: Record<ActionStatus, string> = { planned: '准备开始', doing: '正在实践', done: '已完成', dropped: '已停止' };
type Review = (problemId: string, prompt: string) => void;
/** mode为两个已实现列表；onReview仅交接内存草稿，不发送模型请求。 */
export function PersonalPage({ mode, onReview }: { mode: 'bookmarks' | 'actions'; onReview: Review }) {
  const navigate = useNavigate(), identity = useRef<AbortController | null>(null);
  const [ready, setReady] = useState(false), [failure, setFailure] = useState<ApiFailure | null>(null), [attempt, setAttempt] = useState(0);
  const fail = useCallback((error: ApiFailure) => { identity.current?.abort(); setReady(false); setFailure(error); if (error.status === 401) navigate('/login', { replace: true }); }, [navigate]);
  useEffect(() => {
    let suspended = document.visibilityState === 'hidden';
    /** 无参数；只接受当前会话读取，恢复前不能访问私有接口。 */
    function verify() {
      if (document.visibilityState === 'hidden') return;
      suspended = false; identity.current?.abort(); const request = new AbortController(); identity.current = request;
      setReady(false); setFailure(null);
      readMe(request.signal).then(() => { if (!request.signal.aborted) setReady(true); }).catch(error => { if (!request.signal.aborted) fail(knownFailure(error)); });
    }
    /** 无参数；同步清理收藏笔记与行动观察，晚响应不能恢复旧账号内容。 */
    function hide() { suspended = true; identity.current?.abort(); flushSync(() => { setReady(false); setFailure(null); }); }
    /** 无参数；合并浏览器恢复事件，避免重复读取。 */
    function restore() { if (suspended) verify(); }
    /** 无参数；切换标签同步撤掉私有子树。 */
    function visibility() { if (document.visibilityState === 'hidden') hide(); else restore(); }
    if (!suspended) verify();
    window.addEventListener('pagehide', hide); window.addEventListener('pageshow', restore); document.addEventListener('visibilitychange', visibility);
    return () => { identity.current?.abort(); window.removeEventListener('pagehide', hide); window.removeEventListener('pageshow', restore); document.removeEventListener('visibilitychange', visibility); };
  }, [fail, attempt]);
  return <div className="product-shell reading-shell"><a className="skip-link" href="#main-content">跳转到主要内容</a><AppHeader />
    <main id="main-content" className="reading-main"><PageHero label="让知识走进生活" title={mode === 'bookmarks' ? '我的收藏' : '我的行动'} description={mode === 'bookmarks' ? '留下值得再次阅读的知识，写下自己的理解。' : '从一条建议开始，用真实观察推动下一次思考。'} pose={mode === 'bookmarks' ? 'pose-bookmark' : 'pose-check'} />
      <nav className="personal-tabs" aria-label="个人实践"><Link to="/app/bookmarks" aria-current={mode === 'bookmarks' ? 'page' : undefined}>收藏知识</Link><Link to="/app/actions" aria-current={mode === 'actions' ? 'page' : undefined}>行动与复盘</Link></nav>
      {failure ? <section className="reading-empty"><p role="alert">{failure.status === 404 ? '记录不存在或当前不可访问。' : '暂时无法读取个人记录。'}</p><button type="button" onClick={() => setAttempt(value => value + 1)}>重新读取</button></section> : !ready ? <p role="status">正在确认登录状态…</p> : <Failure.Provider value={fail}><PersonalList mode={mode} onReview={onReview} /></Failure.Provider>}
    </main><footer className="product-footer"><span>第二大脑</span><span>不以读过代替掌握，以实践检验理解。</span></footer></div>;
}
/** mode决定实际接口；分页和筛选变化只接受当前请求，onReview保留同一问题归属。 */
function PersonalList({ mode, onReview }: { mode: 'bookmarks' | 'actions'; onReview: Review }) {
  const fail = useContext(Failure), [cursors, setCursors] = useState<string[]>([]), [status, setStatus] = useState<ActionStatus | ''>('');
  const [page, setPage] = useState<{ items: Bookmark[] | ActionRecord[]; next_cursor: string | null } | null>(null), [refresh, setRefresh] = useState(0);
  const cursor = cursors.at(-1);
  useEffect(() => {
    const request = new AbortController(); setPage(null);
    const load = mode === 'bookmarks' ? readBookmarks({ cursor }, request.signal) : readActions({ cursor, ...(status ? { status } : {}) }, request.signal);
    load.then(value => { if (!request.signal.aborted) setPage(value); }).catch(error => { if (!request.signal.aborted) fail(knownFailure(error)); });
    return () => request.abort();
  }, [mode, cursor, status, refresh, fail]);
  /** 无参数；仅本人显式取消收藏或重读时刷新当前列表。 */
  const reload = () => setRefresh(value => value + 1);
  return <>{mode === 'actions' && <div className="personal-inline"><label htmlFor="action-filter">行动状态</label><select id="action-filter" value={status} onChange={event => { setPage(null); setCursors([]); setStatus(event.target.value as ActionStatus | ''); }}><option value="">全部状态</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>}
    {!page ? <p role="status">正在读取个人记录…</p> : <>{page.items.length === 0 ? <section className="reading-empty"><h2>{mode === 'bookmarks' ? '还没有收藏的知识' : '当前没有行动记录'}</h2><p>{mode === 'bookmarks' ? '打开一张知识卡，点击收藏，就能在这里再次找到它。' : '在分析答案中点击“加入我的行动”，然后回来记录执行情况。'}</p><Link to={mode === 'bookmarks' ? '/app/library' : '/app/problems'}>{mode === 'bookmarks' ? '去书房看看' : '回到我的问题'}</Link></section> : <ul className="personal-records">{mode === 'bookmarks' ? (page.items as Bookmark[]).map(item => <BookmarkRow key={item.id} item={item} reload={reload} />) : (page.items as ActionRecord[]).map(item => <ActionRow key={item.id} item={item} onReview={onReview} />)}</ul>}
      {(cursors.length > 0 || page.next_cursor) && <nav className="personal-inline" aria-label="记录分页"><button type="button" className="secondary-action" disabled={!cursors.length} onClick={() => { setPage(null); setCursors(value => value.slice(0, -1)); }}>上一页</button>{page.next_cursor && <button type="button" className="secondary-action" onClick={() => { setPage(null); setCursors(value => [...value, page.next_cursor!]); }}>下一页</button>}</nav>}</>}
  </>;
}
/** item为当前许可的收藏投影；撤权只能取消，不能显示旧备注或卡片内容。 */
function BookmarkRow({ item, reload }: { item: Bookmark; reload: () => void }) {
  const fail = useContext(Failure), write = useWriteAction(), [note, setNote] = useState(item.note ?? ''), [savedNote, setSavedNote] = useState(item.note ?? ''), [notice, setNotice] = useState('');
  /** error为实际写入失败，失去身份或权限立即卸载本页。 */
  const reject = (error: ApiFailure) => { if (error.status === 401 || error.status === 404) fail(error); };
  return <li className="personal-record"><p className="section-label">收藏知识 · {new Date(item.created_at).toLocaleDateString('zh-CN')}</p>{item.available ? <div className="personal-record-grid"><div><h2><Link to={`/app/library/${item.release_id}/cards/${encodeURIComponent(item.core_card_id)}`}>打开这张知识卡</Link></h2><p className="reading-muted">卡片编号：{item.core_card_id}</p><p>阅读时重新核对当前知识权限，不在收藏中复制原书。</p></div><form onSubmit={event => { event.preventDefault(); const sent = note; void write.run(signal => saveBookmark(item.release_id, item.core_card_id, sent, signal), result => { setSavedNote(result.note ?? ''); setNotice('笔记已保存'); }, reject); }}>
    <label>我的理解与笔记<textarea value={note} maxLength={2000} rows={4} onChange={event => { setNote(event.target.value); setNotice(''); }} placeholder="这条知识为什么值得留下？" /></label><button type="submit" disabled={write.pending || write.seconds > 0 || note === savedNote}>保存笔记</button></form></div> : <><h2>这张收藏当前不可访问</h2><p>知识授权已变化，卡片内容与笔记暂不显示。</p></>}
    <PersonalError failure={write.failure} />{notice && <p role="status">{notice}</p>}<button className="text-action" type="button" disabled={write.pending || write.seconds > 0} onClick={() => void write.run(signal => removeBookmark(item.release_id, item.core_card_id, signal), reload, reject)}>取消这条收藏</button></li>;
}
/** item保存原建议引用，用户只修改执行状态与观察；onReview交接已保存反馈。 */
function ActionRow({ item, onReview }: { item: ActionRecord; onReview: Review }) {
  const fail = useContext(Failure), write = useWriteAction(), [saved, setSaved] = useState(item), [status, setStatus] = useState(item.status), [observation, setObservation] = useState(item.observation), [notice, setNotice] = useState('');
  const dirty = status !== saved.status || observation !== saved.observation;
  /** error为保存失败，冲突保留用户输入，失权清空整个私有页面。 */
  const reject = (error: ApiFailure) => { if (error.status === 401 || error.status === 404) fail(error); };
  /** 无参数；把已保存的实际观察放进同一问题的可编辑框，不自动发起模型。 */
  function review() { onReview(saved.problem_id, `我想复盘之前的行动：${saved.step}\n\n执行状态：${statusLabels[saved.status]}\n实际观察：${saved.observation || '暂未记录具体观察，请先帮我补齐事实。'}\n\n请结合原问题和书中原理，分析哪些假设得到了支持、哪些需要调整，再帮我确定下一步。不要把我的主观观察直接当作已证实的因果结论。`); }
  return <li className="personal-record"><p className="section-label">{statusLabels[saved.status]} · 行动 {saved.action_index + 1}</p><div className="personal-record-grid"><section><h2>{saved.step}</h2><dl><dt>完成标准</dt><dd>{saved.completion_criteria}</dd><dt>观察信号</dt><dd>{saved.validation_signal}</dd><dt>停止条件</dt><dd>{saved.stop_condition}</dd></dl><Link to={`/app/problems/${saved.problem_id}`}>回到原问题与答案</Link></section><form onSubmit={event => { event.preventDefault(); void write.run(signal => updateAction(saved.id, { status, observation, expected_revision: saved.revision }, signal), result => { setSaved(result); setNotice('行动记录已保存'); }, reject); }}>
    <label>执行状态<select value={status} onChange={event => { setStatus(event.target.value as ActionStatus); setNotice(''); }}>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    <label>实际观察<textarea rows={5} maxLength={10000} value={observation} onChange={event => { setObservation(event.target.value); setNotice(''); }} placeholder="做了什么？发生了什么？哪些结果和预想不同？" /></label>
    <PersonalError failure={write.failure} />{notice && <p role="status">{notice}</p>}<button type="submit" disabled={write.pending || write.seconds > 0 || !dirty || write.failure?.status === 409}>保存行动记录</button>
    {write.failure?.status === 409 && <p>请先复制保留当前输入，再刷新页面读取最新记录；不会自动覆盖另一处修改。</p>}
    <button type="button" className="secondary-action" disabled={dirty || write.pending || write.failure?.status === 409} onClick={review}>带着反馈继续和 AI 复盘</button><p className="personal-status">{dirty ? '请先保存，再带着这次反馈继续讨论。' : '只填入原问题的对话框，你确认后才发送。'}</p>
  </form></div></li>;
}
