/** 本人问题列表、创建与详情；服务端档案与消息是真实状态。 */
import { PageHero } from '../journal/Chrome';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeftIcon, ArrowRightIcon, NotePencilIcon } from '@phosphor-icons/react';
import { ApiFailure } from '../../api/client';
import { readLibraries } from '../../api/knowledge';
import { createProblem, readProblem, readProblems, updateProblem } from '../../api/problems';
import type { CreateProblemInput, Problem, UpdateProblemInput } from '../../api/problems';
import { useWriteAction } from '../auth/shared';
import { useProblemFailure, useProblemRead } from './ProblemPage';
import { Conversation } from '../chat/Conversation';
import { TrashProblemControl } from '../privacy/Retention';
import '../../styles/privacy.css';

const goals: Record<Problem['goal'], string> = { explain: '理解一个概念', analyze: '分析一个问题', compare: '比较不同选择', act: '制定行动计划', review: '复盘一次经历' };
/** failure为受控传输错误；creating决定是否提示同键重试，绝不回显自由错误文字。 */
function WriteFailure({ failure, creating = false }: { failure: ApiFailure | null; creating?: boolean }) {
  if (!failure) return null;
  const uncertain = !failure.status || failure.status >= 500 || failure.code === 'INVALID_RESPONSE';
  const message = failure.status === 409 ? (creating ? '提交内容与之前的请求不一致，请检查后重试。' : '其他操作已更新这个问题。请读取最新版本，核对后再次保存；未提交的名称已保留。')
    : uncertain ? (creating ? '暂时无法确认问题是否已保存。草稿已保留，请重试；相同内容会复用本次请求编号。' : '暂时无法确认修改结果。请读取最新版本核对，未提交的名称已保留。')
      : failure.status === 429 ? '操作过于频繁，请稍后再试。' : failure.code === 'RELEASE_UNAVAILABLE' ? '所选知识集当前不可用，请稍后重试或选择其他获准知识集。' : '保存未完成，请检查内容后重试。';
  return <div className="problem-notice" role="alert"><p>{message}</p>{failure.requestId && <small>请求编号：{failure.requestId}</small>}</div>;
}
/** problem为服务端快照；只推导已有澄清状态，不暗示必须追问到上限。 */
function Clarification({ problem }: { problem: Problem }) {
  if (!problem.library_available) return null;
  const state = problem.clarification;
  return <section className="reading-section"><h2>问题澄清</h2>
    <p>{state.closed ? '背景澄清已关闭。' : state.pending_question ? '有一条待回应的澄清问题。' : state.rounds === 0 ? '尚未开始澄清。' : '目前没有待回应的澄清问题。'}</p>
    {state.pending_question && !state.closed && <blockquote className="problem-original">{state.pending_question}</blockquote>}
    {state.rounds > 0 && <p className="reading-muted">已进行 {state.rounds} 轮澄清。是否继续取决于问题需要。</p>}
  </section>;
}
/** 无参数；只读取当前页，搜索/状态变化重置游标，不累计私有问题内容。 */
export function ProblemCatalog() {
  const [draft, setDraft] = useState(''), [query, setQuery] = useState('');
  const [status, setStatus] = useState<Problem['status']>('active'), [cursor, setCursor] = useState<string>();
  const load = useCallback((signal: AbortSignal) => readProblems({ q: query, status, ...(cursor ? { cursor } : {}) }, signal), [query, status, cursor]);
  const page = useProblemRead(load);
  return <section><PageHero label="思考的起点" title="我的问题" description="把真实困惑写下来，也为以后的思考留一份记录。" pose="pose-walk"
      action={<Link className="problem-primary-link" to="/app/problems/new"><NotePencilIcon size={19} aria-hidden="true" />新建问题</Link>} />
    <div className="reading-mode"><div>{(['active', 'archived'] as const).map(value => <button key={value} type="button" aria-pressed={status === value} onClick={() => { setStatus(value); setCursor(undefined); }}>{value === 'active' ? '进行中' : '已归档'}</button>)}</div><Link to="/app/trash">问题回收站</Link></div>
    <form className="library-search" onSubmit={event => { event.preventDefault(); setQuery(draft); setCursor(undefined); }}><div className="reading-field search-keyword"><label htmlFor="problem-search">搜索我的问题</label><input id="problem-search" value={draft} maxLength={500} onChange={event => setDraft(event.target.value)} autoComplete="off" /></div><button type="submit">搜索</button></form>
    {!page ? <p className="reading-status" role="status">正在读取问题…</p> : <><p className="reading-count">本页 {page.items.length} 个问题</p>
      {!page.items.length ? <div className="reading-empty"><h2>{query ? '没有找到符合条件的问题' : status === 'archived' ? '还没有归档的问题' : '从一个真实问题开始'}</h2><p>{query ? '可以换一个关键词，或切换问题状态。' : '保存问题后，你可以随时回来查看原文和整理名称。'}</p></div>
        : <ul className="problem-list">{page.items.map(problem => <li key={problem.id}><div><h2><Link to={`/app/problems/${problem.id}`}>{problem.title}</Link></h2><p>{goals[problem.goal]} · {problem.status === 'archived' ? '已归档' : '进行中'} · 修订 {problem.revision}</p>{!problem.library_available && <p>绑定的知识集当前不可用</p>}</div><ArrowRightIcon size={20} aria-hidden="true" /></li>)}</ul>}
      {(cursor || page.next_cursor) && <nav className="reading-pagination" aria-label="问题分页">{cursor && <button type="button" onClick={() => setCursor(undefined)}>返回第一页</button>}{page.next_cursor && <button type="button" onClick={() => setCursor(page.next_cursor!)}>下一页</button>}</nav>}
    </>}
  </section>;
}
/** 无参数；问题和幂等键仅驻留当前表单，同一提交结果不明时保留键等待明确重试。 */
export function ProblemCreate() {
  const navigate = useNavigate(), fail = useProblemFailure(), action = useWriteAction();
  const [question, setQuestion] = useState(''), [goal, setGoal] = useState<Problem['goal']>('analyze');
  const [cursor, setCursor] = useState<string>(), [selection, setSelection] = useState('');
  const submitted = useRef<{ signature: string; key: string } | null>(null);
  const load = useCallback((signal: AbortSignal) => readLibraries(cursor ? { cursor } : {}, signal), [cursor]);
  const page = useProblemRead(load);
  const release = page?.items.find(item => item.id === selection)?.id ?? page?.items[0]?.id;
  const count = Array.from(question).length;
  /** 无参数；校验当前内存内容，只发送一次创建请求，不触发分析或消息消费。 */
  function save() {
    if (!release || !question.trim() || count > 4000 || action.pending) return;
    const data: CreateProblemInput = { question, goal, release_id: release };
    const signature = JSON.stringify(data);
    if (submitted.current?.signature !== signature) submitted.current = { signature, key: crypto.randomUUID() };
    const key = submitted.current.key;
    void action.run(signal => createProblem(data, key, signal), value => navigate(`/app/problems/${value.id}`, { replace: true }), error => { if (error.status === 401 || error.status === 404) fail(error); });
  }
  return <section className="problem-compose"><Link className="reading-back" to="/app/problems"><ArrowLeftIcon size={17} aria-hidden="true" />返回我的问题</Link>
    <PageHero label="留下一份真实表达" title="你正在想什么？" description="困惑、选择或一段想复盘的经历，都可以从这里开始。你的原话会完整保存。" pose="pose-write" />
    {!page ? <p className="reading-status" role="status">正在读取获准知识集…</p> : !page.items.length ? <section className="reading-empty"><h2>当前没有获准的知识集</h2><p>保存问题需要绑定一个获准知识集。当前还不能保存，请先回书房查看访问情况。</p><Link to="/app/library">返回书房</Link>{cursor && <button type="button" onClick={() => { setCursor(undefined); setSelection(''); }}>返回知识集第一页</button>}</section>
      : <form className="problem-form" onSubmit={event => { event.preventDefault(); save(); }}>
        <div className="reading-field"><label htmlFor="original-question">你的问题</label><textarea id="original-question" value={question} onChange={event => setQuestion(event.target.value)} disabled={action.pending} rows={7} required aria-describedby="question-help" autoComplete="off" placeholder="例如：我想换一份工作，但不确定自己是在逃避眼前的困难，还是确实需要改变……" /><p id="question-help" className="reading-muted">{count} / 4000 字符 · 回车换行，按原样保存。{count > 4000 ? ' 请缩短至 4000 字符以内。' : ''}</p></div>
        <div className="problem-form-row"><div className="reading-field"><label htmlFor="problem-goal">这次想做什么</label><select id="problem-goal" value={goal} disabled={action.pending} onChange={event => setGoal(event.target.value as Problem['goal'])}>{Object.entries(goals).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
          <div className="reading-field"><label htmlFor="problem-release">绑定知识集</label><select id="problem-release" value={release} disabled={action.pending} onChange={event => setSelection(event.target.value)}>{page.items.map(item => <option value={item.id} key={item.id}>{item.title} · {item.book_count} 本书</option>)}</select></div></div>
        {(cursor || page.next_cursor) && <div className="reading-pagination">{cursor && <button className="text-action" type="button" disabled={action.pending} onClick={() => { setCursor(undefined); setSelection(''); }}>返回知识集第一页</button>}{page.next_cursor && <button className="text-action" type="button" disabled={action.pending} onClick={() => { setCursor(page.next_cursor!); setSelection(''); }}>下一页知识集</button>}</div>}
        <p className="problem-notice">此处只保存问题并绑定所选知识版本。保存后可以继续对话，保存本身不会启动模型分析。</p>
        <WriteFailure failure={action.failure} creating />
        <div className="problem-actions"><button type="submit" disabled={action.pending || action.seconds > 0 || !question.trim() || count > 4000}>{action.pending ? '正在保存…' : action.seconds ? `${action.seconds} 秒后可重试` : '保存问题'}<ArrowRightIcon size={18} aria-hidden="true" /></button><span className="reading-muted">未保存的文字仅保留在当前可见页面。</span></div>
      </form>}
  </section>;
}
/** id为公开问题UUID；保留未提交名称，冲突后仅手动重读并等待再次确认保存。 */
export function ProblemDetail({ id, initialDraft, onDraftUsed }: { id: string; initialDraft?: string; onDraftUsed?: () => void }) {
  const fail = useProblemFailure(), action = useWriteAction();
  const [problem, setProblem] = useState<Problem | null>(null), [title, setTitle] = useState('');
  const [reload, setReload] = useState(0), [loading, setLoading] = useState(true), [conflict, setConflict] = useState(false);
  const [notice, setNotice] = useState('');
  /** revision/available来自已校验消息页，只提升修订并同步当前知识许可。 */
  const onRevision = useCallback((revision: number, available: boolean) => setProblem(current => current ? { ...current, revision: Math.max(current.revision, revision), library_available: available } : current), []);
  /** value为后台新快照；拒绝倒退修订，名称输入和聊天草稿不重置。 */
  const onProblem = useCallback((value: Problem) => setProblem(current => current && value.revision >= current.revision ? value : current), []);
  useEffect(() => {
    const request = new AbortController(); setLoading(true);
    readProblem(id, request.signal).then(value => {
      if (request.signal.aborted) return;
      setProblem(value); if (!reload) setTitle(value.title); setConflict(false); setLoading(false);
      if (reload) setNotice('已读取最新版本。请核对当前名称与修订，再决定是否保存你的名称。');
    }).catch(error => { if (!request.signal.aborted) fail(error); });
    return () => request.abort();
  }, [id, reload, fail]);
  /** data为名称或归档变更；修订来自当前已读快照，不在冲突后自动覆盖。 */
  function change(data: Omit<UpdateProblemInput, 'expected_revision'>) {
    if (!problem || loading || conflict) return;
    setNotice('');
    void action.run(signal => updateProblem(id, { ...data, expected_revision: problem.revision }, signal), value => { setProblem(value); if (data.title !== undefined) setTitle(value.title); setNotice('修改已保存。'); }, error => { if (error.status === 401 || error.status === 404) fail(error); else if (error.status === 409) setConflict(true); });
  }
  const pending = loading || action.pending || action.seconds > 0;
  return <article className="problem-detail"><Link className="reading-back" to="/app/problems"><ArrowLeftIcon size={17} aria-hidden="true" />返回我的问题</Link>
    {!problem ? <p className="reading-status" role="status">正在读取问题…</p> : <><div className="reading-heading"><p className="section-label">{problem.status === 'archived' ? '已归档' : '进行中'} · 修订 {problem.revision}</p><h1>{problem.title}</h1><p>{goals[problem.goal]}</p></div>
      <section className="reading-section"><h2>你最初的问题</h2><p className="problem-original">{problem.original_question}</p></section>
      {!problem.library_available && <p className="problem-notice">绑定的知识集当前不可用。这里保留你本人的问题原文，暂时无法读取相关知识。</p>}
      <Clarification problem={problem} /><Conversation problem={problem} onRevision={onRevision} onProblem={onProblem} initialDraft={initialDraft} onDraftUsed={onDraftUsed} />
    </>}
    {problem && <section className="reading-section"><h2>整理这个问题</h2><p className="reading-muted">修改名称不会改写你最初的问题。</p>
      <form className="problem-rename" onSubmit={event => { event.preventDefault(); if (title.trim() && Array.from(title).length <= 160) change({ title }); }}><div className="reading-field"><label htmlFor="problem-title">问题名称</label><input id="problem-title" value={title} disabled={pending} required onChange={event => setTitle(event.target.value)} autoComplete="off" /></div><button type="submit" disabled={pending || conflict || !title.trim() || Array.from(title).length > 160 || title === problem.title}>保存名称</button></form>
      {Array.from(title).length > 160 && <p role="alert">名称最多 160 个字符。</p>}
      {action.failure && !notice && <WriteFailure failure={action.failure} />}{notice && <p role="status">{notice}</p>}
      <div className="problem-actions">{(conflict || action.failure) && <button type="button" disabled={pending} onClick={() => { setNotice(''); setReload(value => value + 1); }}>读取最新版本</button>}<button className="secondary-action" type="button" disabled={pending || conflict} onClick={() => change({ status: problem.status === 'active' ? 'archived' : 'active' })}>{problem.status === 'active' ? '归档问题' : '恢复归档'}</button>{action.seconds > 0 && <span>{action.seconds} 秒后可重试</span>}</div>
      <TrashProblemControl id={problem.id} revision={problem.revision} disabled={pending || conflict} onFailure={fail} />
    </section>}
  </article>;
}