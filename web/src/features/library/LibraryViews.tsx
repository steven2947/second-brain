/** 知识集/书目/卡片阅读视图，只展示公开DTO，不生成未存在的分析或收藏行为。 */
import { PageHero } from '../journal/Chrome';
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeftIcon, ArrowRightIcon, BookOpenIcon, ListIcon, SquaresFourIcon, MagnifyingGlassIcon } from '@phosphor-icons/react';
import { readLibraries, readBooks, readBook, readCards, readCard, readEvidence } from '../../api/knowledge';
import { ApiFailure } from '../../api/client';
import type { PublicBook, BookPage, CardPage, CardSummary, CardQuery, SourcePreview } from '../../api/knowledge';
import { ReadingStatus, useLibraryRead, useLibraryFailure } from './LibraryPage';
import { BookmarkControl } from '../personal/PersonalControls';

// 对应知识卡schema的kind枚举；未知新值仍按服务端公开文字展示。
const cardTypes: Record<string, string> = { claim: '观点', definition: '定义', concept: '概念', principle: '原理', method: '方法', case: '案例', counterexample: '反例', evidence: '证据', critique: '评析', question: '问题' };

/** book为已解码公开书目；缺少作者时不猜测归属。 */
function author(book: PublicBook) { return book.author_display || '作者信息待核实'; }
/** release/id为稳定公开标识，kind限定现有详情路由。 */
function detailLink(release: string, kind: 'books' | 'cards', id: string) { return `/app/library/${encodeURIComponent(release)}/${kind}/${encodeURIComponent(id)}`; }
/** release为固定知识版本；返回时仅携带版本ID，不持久化查询内容。 */
function BackToLibrary({ release }: { release: string }) { return <Link className="reading-back" to={`/app/library?release=${encodeURIComponent(release)}`}><ArrowLeftIcon size={17} aria-hidden="true" />返回知识库</Link>; }
/** next为服务器签名游标，back为已走过游标；这里只切页，不猜测总页数。 */
function Pager({ next, back, onNext, onBack }: { next: string | null; back: boolean; onNext: (cursor: string) => void; onBack: () => void }) {
  return (next || back) ? <nav className="reading-pagination" aria-label="结果分页"><button className="secondary-action" type="button" onClick={onBack} disabled={!back}><ArrowLeftIcon size={17} aria-hidden="true" />上一页</button>{next && <button className="secondary-action" type="button" onClick={() => onNext(next)}>下一页<ArrowRightIcon size={17} aria-hidden="true" /></button>}</nav> : null;
}
/** initialRelease为URL里的可选稳定版本；版本列表从当前账号获准接口读取。 */
export function LibraryCatalog({ initialRelease }: { initialRelease?: string }) {
  const [cursors, setCursors] = useState<string[]>([]), [selected, setSelected] = useState(initialRelease ?? '');
  const cursor = cursors.at(-1);
  const load = useCallback((signal: AbortSignal) => readLibraries({ limit: 20, cursor }, signal), [cursor]);
  const page = useLibraryRead(load);
  if (!page) return <ReadingStatus />;
  const current = selected || page.items[0]?.id;
  return <><PageHero label="午后好时光" title="我的书房" description="浏览获准知识集，沿着观点回到出处。" pose="pose-shelf" />
    <div className="catalog-heading-row">
      {page.items.length > 0 && <div className="release-summary"><div className="release-picker"><label htmlFor="release-choice">知识集</label><select id="release-choice" value={current} onChange={event => setSelected(event.target.value)}>{!page.items.some(item => item.id === current) && <option value={current}>指定知识版本</option>}{page.items.map(item => <option key={item.id} value={item.id}>{item.title} · {item.book_count} 本书 · {item.card_count} 张卡片</option>)}</select></div>
      {page.items.find(item => item.id === current)?.description && <p className="reading-muted">{page.items.find(item => item.id === current)!.description}</p>}</div>}</div>
    {page.items.length === 0 ? <section className="reading-empty"><BookOpenIcon size={35} aria-hidden="true" /><h2>暂无可访问的知识集</h2><p>当前账号还没有可浏览的知识版本。</p></section> : <>
      {current && <CatalogResults key={current} release={current} />}
    </>}
    {(page.next_cursor || cursors.length > 0) && <section className="release-pagination"><p className="reading-muted">知识集分页</p><Pager next={page.next_cursor} back={cursors.length > 0} onNext={value => { setSelected(''); setCursors(values => [...values, value]); }} onBack={() => { setSelected(''); setCursors(values => values.slice(0, -1)); }} /></section>}
  </>;
}
/** release为当前版本；查询仅在表单提交时改变，切模式与版本清空游标。 */
function CatalogResults({ release }: { release: string }) {
  const [mode, setMode] = useState<'books' | 'cards'>('books');
  const [query, setQuery] = useState<CardQuery>({});
  const [draft, setDraft] = useState({ q: '', author: '', book: '', type: '' });
  const [shelf, setShelf] = useState(true), [submission, setSubmission] = useState(0);
  /** next是用户选择的阅读模式；重建表单和查询，避免跨模式残留。 */
  function changeMode(next: 'books' | 'cards') { setMode(next); setQuery({}); setDraft({ q: '', author: '', book: '', type: '' }); setSubmission(value => value + 1); }
  return <section className="catalog-content" aria-label="知识内容">
    <div className="reading-mode"><div role="group" aria-label="浏览内容"><button type="button" aria-pressed={mode === 'books'} onClick={() => changeMode('books')}>书籍</button><button type="button" aria-pressed={mode === 'cards'} onClick={() => changeMode('cards')}>知识卡片</button></div>{mode === 'books' && <div role="group" aria-label="书目显示方式"><button type="button" aria-pressed={shelf} onClick={() => setShelf(true)}><SquaresFourIcon size={18} aria-hidden="true" />书架</button><button type="button" aria-pressed={!shelf} onClick={() => setShelf(false)}><ListIcon size={18} aria-hidden="true" />列表</button></div>}</div>
    <form className="library-search" onSubmit={event => { event.preventDefault(); setQuery({ q: draft.q.trim(), author: draft.author.trim(), ...(mode === 'cards' ? { book: draft.book.trim(), type: draft.type.trim() } : {}) }); setSubmission(value => value + 1); }}>
      <div className="reading-field search-keyword"><label htmlFor="knowledge-query">关键词</label><input id="knowledge-query" autoComplete="off" maxLength={500} value={draft.q} onChange={event => setDraft(value => ({ ...value, q: event.target.value }))} placeholder={mode === 'books' ? '搜索书名' : '搜索观点、原理或方法'} /></div>
      <div className="reading-field"><label htmlFor="knowledge-author">作者</label><input id="knowledge-author" autoComplete="off" maxLength={240} value={draft.author} onChange={event => setDraft(value => ({ ...value, author: event.target.value }))} placeholder="作者名称" /></div>
      {mode === 'cards' && <><BookChooser release={release} value={draft.book} onChange={book => setDraft(value => ({ ...value, book }))} /><div className="reading-field"><label htmlFor="knowledge-type">卡片类型</label><select id="knowledge-type" value={draft.type} onChange={event => setDraft(value => ({ ...value, type: event.target.value }))}><option value="">全部类型</option>{Object.entries(cardTypes).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div></>}
      <button type="submit"><MagnifyingGlassIcon size={18} aria-hidden="true" />搜索</button>
    </form><p className="reading-muted search-note">{mode === 'books' ? '按书名与作者筛选。' : '按关键词、作者、书籍与类型筛选。'}填写后点击搜索。</p>
    <Results key={`${mode}-${submission}`} release={release} mode={mode} query={query} shelf={shelf} />
  </section>;
}
/** release限定下拉选项，value/onChange是尚未提交的书籍选择；按需加载更多，不预取整库。 */
function BookChooser({ release, value, onChange }: { release: string; value: string; onChange: (book: string) => void }) {
  const [cursor, setCursor] = useState<string>(), [options, setOptions] = useState<PublicBook[]>([]);
  const load = useCallback((signal: AbortSignal) => readBooks(release, { limit: 20, cursor }, signal), [release, cursor]);
  const page = useLibraryRead(load);
  useEffect(() => { if (page) setOptions(previous => [...previous, ...page.items.filter(book => !previous.some(existing => existing.id === book.id))]); }, [page]);
  return <div className="reading-field"><label htmlFor="knowledge-book">书籍</label><select id="knowledge-book" value={value} onChange={event => onChange(event.target.value)}><option value="">全部书籍</option>{options.map(book => <option key={book.id} value={book.id}>{book.title}</option>)}</select>{!page ? <span className="reading-muted" role="status">正在读取书籍选项…</span> : page.next_cursor && <button className="text-action" type="button" onClick={() => setCursor(page.next_cursor!)}>更多书籍</button>}</div>;
}
/** release/mode/query确定读取范围，shelf只改变布局，不重新请求。 */
function Results({ release, mode, query, shelf = false }: { release: string; mode: 'books' | 'cards'; query: CardQuery; shelf?: boolean }) {
  const [cursors, setCursors] = useState<string[]>([]);
  const cursor = cursors.at(-1);
  const load = useCallback((signal: AbortSignal): Promise<BookPage | CardPage> => mode === 'books' ? readBooks(release, { ...query, limit: 20, cursor }, signal) : readCards(release, { ...query, limit: 20, cursor }, signal), [release, mode, query, cursor]);
  const page = useLibraryRead(load);
  if (!page) return <ReadingStatus />;
  return <><p className="reading-count">本页 {page.items.length} {mode === 'books' ? '本书' : '张知识卡片'}</p>{page.items.length === 0 ? <p className="reading-empty">没有符合条件的{mode === 'books' ? '书籍' : '知识卡片'}，可以调整筛选条件。</p> : mode === 'books' ? <ul className={shelf ? 'book-shelf' : 'book-list'}>{(page.items as PublicBook[]).map(book => <li key={book.id}>
      {shelf && <div className="text-cover" aria-hidden="true"><span>知识书目</span><strong>{book.title}</strong><small>{author(book)}</small></div>}
      <div className="book-caption"><h2><Link to={detailLink(release, 'books', book.id)}>{book.title}</Link></h2><p>{author(book)}</p>{book.metadata_status === 'partial' && <span>书目信息待完善</span>}</div>
    </li>)}</ul> : <ul className="knowledge-list">{(page.items as CardSummary[]).map(card => <li key={card.card_id}><span className="section-label">{cardTypes[card.type] || card.type} · {card.book.title}</span><h3><Link to={detailLink(release, 'cards', card.card_id)}>{card.title}</Link></h3><p>{card.statement}</p><span className="reading-muted">{author(card.book)}</span></li>)}</ul>}
    <Pager next={page.next_cursor} back={cursors.length > 0} onNext={value => setCursors(values => [...values, value])} onBack={() => setCursors(values => values.slice(0, -1))} /></>;
}
/** release/id是路由中的固定书目；章节只表示证据覆盖，不表示可阅读原书全文。 */
export function BookReader({ release, id }: { release: string; id: string }) {
  const load = useCallback((signal: AbortSignal) => readBook(release, id, signal), [release, id]);
  const book = useLibraryRead(load);
  const [query] = useState<CardQuery>({ book: id });
  if (!book) return <ReadingStatus />;
  return <><BackToLibrary release={release} /><header className="reading-heading"><p className="section-label">书籍详情</p><h1>{book.title}</h1><p>{author(book)}</p></header>
    <section className="reading-section"><h2>章节覆盖</h2><p className="reading-muted">以下章节已有来源证据，并非原书全文目录。</p><TextList values={book.chapters} empty="暂无可展示的章节覆盖" /></section>
    <section className="reading-section"><h2>已知缺口</h2><TextList values={book.gaps} empty="当前接口未报告覆盖缺口，不代表全书已完整覆盖。" /></section>
    <section className="reading-section"><h2>这本书的知识卡片</h2><Results release={release} mode="cards" query={query} /></section>
  </>;
}
/** values为完整条目数组；empty是没有数据时的固定说明，ordered为方法步骤。 */
function TextList({ values, empty, ordered = false }: { values: string[]; empty: string; ordered?: boolean }) {
  if (!values.length) return <p className="reading-muted">{empty}</p>;
  const List = ordered ? 'ol' : 'ul';
  return <List className="reading-text-list">{values.map((value, index) => <li key={index}>{value || '此条目未填写'}</li>)}</List>;
}
const claims = { author_claim: '作者观点', quoted_other: '书中引用他人观点', system_inference: '系统推断', unknown: '观点归属待核实' };
const relations: Record<string, string> = { depends_on: '依赖', contrasts_with: '对照', composes_with: '组合', limited_by: '受限于' };
/** release/id固定卡片读取范围；保留原卡的完整原理和来源归属。 */
export function CardReader({ release, id }: { release: string; id: string }) {
  const fail = useLibraryFailure();
  const load = useCallback((signal: AbortSignal) => readCard(release, id, signal), [release, id]);
  const card = useLibraryRead(load);
  if (!card) return <ReadingStatus />;
  return <article className="card-reader"><BackToLibrary release={release} /><header className="reading-heading"><p className="section-label">{cardTypes[card.type] || card.type} · {claims[card.source_claim_type]}</p><h1>{card.title}</h1><p><Link to={detailLink(release, 'books', card.book.id)}>{card.book.title}</Link> · {author(card.book)}</p></header>
    <aside className="usage-notice">整理内容，未针对当前问题采用</aside>
    <BookmarkControl key={`${release}/${id}`} release={release} card={id} onFailure={fail} />
    <section className="reading-section"><h2>核心观点</h2><p className="principle-statement">{card.statement}</p></section>
    <section className="reading-section"><h2>原理解释</h2><p>{card.explanation || '当前卡片未提供原理解释。'}</p></section>
    <section className="reading-section"><h2>适用条件</h2><TextList values={card.conditions} empty="当前卡片未提供适用条件。" /></section>
    <section className="reading-section"><h2>边界与限制</h2><TextList values={card.boundaries} empty="当前卡片未提供边界说明。" /></section>
    <section className="reading-section"><h2>操作步骤</h2><TextList values={card.steps} empty="当前卡片未提供操作步骤。" ordered /></section>
    <section className="reading-section"><h2>应用说明</h2><p>{card.application_notes || '当前卡片未提供应用说明。'}</p></section>
    <section className="reading-section"><h2>关联知识</h2>{!card.related.length ? <p className="reading-muted">暂无可展示的关联。</p> : <ul className="relation-list">{card.related.map(relation => {
      const outgoing = relation.from_id === card.card_id, target = outgoing ? relation.to_id : relation.from_id;
      return <li key={relation.id}><p><span>{outgoing ? '本卡 → 关联卡' : '关联卡 → 本卡'} · {relations[relation.type] || relation.type}</span><span className="reading-muted"> · {relation.basis === 'source' ? '原文依据' : '系统推断'}</span></p><Link to={detailLink(release, 'cards', target)}>查看关联知识</Link><p>{relation.rationale || '未提供关系说明。'}</p></li>;
    })}</ul>}</section>
    <section className="reading-section"><h2>来源预览</h2><p className="reading-muted">原文短引保留来源给出的文字与位置。预览不等于完整原书。</p>{card.source_previews.length ? card.source_previews.map(source => <SourceReading key={source.evidence_id} source={source} />) : <p>暂无可展示的来源预览，可能尚未收录或当前未获准访问。</p>}</section>
    <section className="reading-section"><h2>已知缺口</h2><TextList values={card.gaps} empty="当前接口未报告其他缺口。" /></section>
  </article>;
}
/** source是已获准短引；重新读取实际证据接口，旧预览在请求过程中卸载。 */
function SourceReading({ source }: { source: SourcePreview }) {
  const [revision, setRevision] = useState(0);
  return <div className="source-reading">{revision === 0 ? <SourceText source={source} /> : <ReloadedSource key={revision} release={source.release_id} id={source.evidence_id} expectedBookId={source.book.id} />}<button type="button" className="text-action" onClick={() => setRevision(value => value + 1)}>重新读取此来源</button></div>;
}
/** release/id为服务端允许的证据标识，expectedBookId保持原卡的书籍归属。 */
function ReloadedSource({ release, id, expectedBookId }: { release: string; id: string; expectedBookId: string }) {
  const load = useCallback(async (signal: AbortSignal) => {
    const source = await readEvidence(release, id, signal);
    if (source.book.id !== expectedBookId) throw new ApiFailure('INVALID_RESPONSE');
    return source;
  }, [release, id, expectedBookId]);
  const source = useLibraryRead(load);
  return source ? <SourceText source={source} /> : <ReadingStatus />;
}
/** source为原文连续短引；字符范围严格按接口数值显示，绝不换算页码。 */
function SourceText({ source }: { source: SourcePreview }) {
  return <><h3>{source.book.title} · {source.chapter || '章节信息未提供'}</h3><p className="reading-muted">{author(source.book)}</p><blockquote>{source.text}</blockquote><p className="reading-muted">{source.truncated ? '此预览已截断，仅展示部分连续原文。' : '此预览未截断，仍仅代表这一证据片段。'}</p><p className="source-location">{source.location.kind === 'original' ? '正文字符位置' : '证据汇编字符位置'}：{source.location.start}–{source.location.end}{source.location.paragraph_id ? ` · 段落 ${source.location.paragraph_id}` : ''}</p><p className="reading-muted">{source.location.notice}</p></>;
}