/** 学习列表和选卡创建；创建只保存目标，不自动开始模型调用。 */
import { PageHero } from '../journal/Chrome';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { readCards, readLibraries } from '../../api/knowledge';
import type { CardPage, CardSummary, LibraryPage } from '../../api/knowledge';
import { createLearning, listLearning } from '../../api/learning';
import type { CreateLearning, LearningSession } from '../../api/learning';
import { knownFailure, useWriteAction } from '../auth/shared';
import { LearningError, useLearningFailure } from './LearningPage';

/** 无参数；读取本人当前或归档学习，分页不缓存到浏览器存储。 */
export function LearningCatalog() {
  const fail = useLearningFailure(), [status, setStatus] = useState<'active' | 'archived'>('active'), [cursors, setCursors] = useState<string[]>([]);
  const [page, setPage] = useState<{ items: LearningSession[]; next_cursor: string | null } | null>(null), cursor = cursors.at(-1);
  useEffect(() => { const request = new AbortController(); setPage(null); listLearning({ status, ...(cursor ? { cursor } : {}) }, request.signal).then(value => { if (!request.signal.aborted) setPage(value); }).catch(error => { if (!request.signal.aborted) fail(knownFailure(error)); }); return () => request.abort(); }, [status, cursor, fail]);
  return <><PageHero label="我的学习室" title="让知识，变成自己的理解。" description="从感兴趣的知识卡开始，读懂原理，尝试应用，再带着疑问继续深入。" pose="pose-sparkle" action={<Link className="primary-action learning-link" to="/app/learning/new">开始一次学习</Link>} />
    <div className="learning-toolbar"><label>学习记录<select value={status} onChange={event => { setPage(null); setCursors([]); setStatus(event.target.value as 'active' | 'archived'); }}><option value="active">正在学习</option><option value="archived">已经归档</option></select></label></div>
    {!page ? <p role="status">正在读取学习记录…</p> : <>{page.items.length ? <ul className="learning-session-list">{page.items.map(item => <li key={item.id}><span className="section-label">{item.basis_card_ids.length} 张知识卡 · {new Date(item.updated_at).toLocaleDateString('zh-CN')}</span><h2><Link to={`/app/learning/${item.id}`}>{item.title}</Link></h2><p>{item.goal}</p><Link to={`/app/learning/${item.id}`}>{item.status === 'archived' ? '回看学习内容' : '继续学习'} →</Link></li>)}</ul> : <section className="reading-empty"><h2>{status === 'active' ? '还没有开始的学习' : '还没有归档记录'}</h2><p>不用先提出一个现实问题。选几张感兴趣的卡片，就可以从原理开始。</p></section>}
      <nav className="learning-toolbar" aria-label="学习列表分页"><button type="button" disabled={!cursors.length} onClick={() => setCursors(value => value.slice(0, -1))}>上一页</button><button type="button" disabled={!page.next_cursor} onClick={() => page.next_cursor && setCursors(value => [...value, page.next_cursor!])}>下一页</button></nav></>}
  </>;
}

/** 无参数；选中知识固定在同一release，搜索翻页保留选择，切换版本才清空选择。 */
export function LearningCreate() {
  const fail = useLearningFailure(), navigate = useNavigate(), write = useWriteAction();
  const [libraries, setLibraries] = useState<LibraryPage | null>(null), [release, setRelease] = useState(''), [libraryCursor, setLibraryCursor] = useState<string | undefined>();
  const [query, setQuery] = useState(''), [search, setSearch] = useState(''), [cardCursor, setCardCursor] = useState<string | undefined>(), [page, setPage] = useState<CardPage | null>(null);
  const [selected, setSelected] = useState<CardSummary[]>([]), [goal, setGoal] = useState('');
  const pending = useRef<{ digest: string; key: string } | null>(null);
  useEffect(() => { const request = new AbortController(); readLibraries({ ...(libraryCursor ? { cursor: libraryCursor } : {}) }, request.signal).then(value => { if (!request.signal.aborted) setLibraries(value); }).catch(error => { if (!request.signal.aborted) fail(knownFailure(error)); }); return () => request.abort(); }, [libraryCursor, fail]);
  useEffect(() => { setPage(null); if (!release) return; const request = new AbortController(); readCards(release, { q: search, limit: 20, ...(cardCursor ? { cursor: cardCursor } : {}) }, request.signal).then(value => { if (!request.signal.aborted) setPage(value); }).catch(error => { if (!request.signal.aborted) fail(knownFailure(error)); }); return () => request.abort(); }, [release, search, cardCursor, fail]);
  /** item为本次真实搜索卡片；移除或新增都不影响其他已选卡片。 */
  function select(item: CardSummary) { setSelected(value => value.some(card => card.card_id === item.card_id) ? value.filter(card => card.card_id !== item.card_id) : [...value, item]); }
  /** 无参数；提交目标和ID，没有讲解占位答案，也不自动消费模型。 */
  function create() {
    const data: CreateLearning = { release_id: release, basis_card_ids: selected.map(card => card.card_id), goal };
    const digest = JSON.stringify(data); if (pending.current?.digest !== digest) pending.current = { digest, key: crypto.randomUUID() };
    void write.run(signal => createLearning(data, pending.current!.key, signal), result => navigate(`/app/learning/${result.id}`), error => { if (error.status === 401 || error.status === 404) fail(error); });
  }
  return <><Link to="/app/learning">← 我的学习</Link><header className="reading-heading"><p className="section-label">从好奇心开始</p><h1>这次，你想弄懂什么？</h1><p>先选知识卡，再写下想理解或应用的方向。创建后，你决定何时开始讲解。</p></header>
    {!libraries ? <p role="status">正在读取可用知识库…</p> : !libraries.items.length ? <section className="reading-empty"><h2>当前没有获准知识库</h2><p>需要管理员先发布并授权知识版本，之后才能选卡学习。</p></section> : <div className="learning-create-grid"><section className="learning-picker" aria-label="选择知识卡">
      <label>知识库<select value={release} disabled={write.pending} onChange={event => { setPage(null); setRelease(event.target.value); setSelected([]); setCardCursor(undefined); setSearch(''); setQuery(''); }}><option value="">请选择一个知识版本</option>{libraries.items.map(item => <option key={item.id} value={item.id}>{item.title} · {item.book_count} 本书</option>)}</select></label>
      {(libraryCursor || libraries.next_cursor) && <div className="learning-toolbar"><button type="button" disabled={write.pending} onClick={() => { setRelease(''); setSelected([]); setLibraries(null); setLibraryCursor(libraries.next_cursor ?? undefined); }}>{libraries.next_cursor ? '下一页知识库' : '回到第一页知识库'}</button></div>}
      {release && <><form className="learning-search" onSubmit={event => { event.preventDefault(); setCardCursor(undefined); setSearch(query); }}><label>搜索知识<input value={query} maxLength={500} onChange={event => setQuery(event.target.value)} placeholder="例如：机会成本、反馈、决策" /></label><button type="submit">搜索</button></form>
        {!page ? <p role="status">正在读取知识卡…</p> : <><ul className="learning-card-options">{page.items.map(item => <li key={item.card_id}><label><input type="checkbox" disabled={write.pending} checked={selected.some(card => card.card_id === item.card_id)} onChange={() => select(item)} /><span><strong>{item.title}</strong><small>《{item.book.title}》 · {item.book.author_display ?? '作者待核实'}</small><span>{item.statement}</span></span></label></li>)}</ul>{!page.items.length && <p>没有找到匹配卡片，试试更换关键词。</p>}<div className="learning-toolbar">{cardCursor && <button type="button" onClick={() => setCardCursor(undefined)}>回到首批</button>}{page.next_cursor && <button type="button" onClick={() => setCardCursor(page.next_cursor!)}>下一批知识卡</button>}</div></>}
      </>}
    </section><form className="learning-plan" onSubmit={event => { event.preventDefault(); create(); }}><p className="section-label">这次学习的起点</p><h2>已选 {selected.length} 张知识卡</h2><ul>{selected.map(item => <li key={item.card_id}><span>{item.title}</span><button type="button" className="text-action" disabled={write.pending} aria-label={`移除${item.title}`} onClick={() => select(item)}>移除</button></li>)}</ul>
      <label>学习目标<textarea value={goal} disabled={write.pending} rows={6} maxLength={4000} required onChange={event => setGoal(event.target.value)} placeholder="例如：我想弄清楚这些方法的原理，以及什么时候用反而会出错。" /></label><LearningError error={write.failure} /><button type="submit" disabled={!release || !selected.length || !goal.trim() || write.pending || write.seconds > 0}>{write.pending ? '正在保存…' : '创建学习，进入学习室'}</button><p className="reading-muted">这一步只保存目标，不调用 AI。</p>
    </form></div>}
  </>;
}