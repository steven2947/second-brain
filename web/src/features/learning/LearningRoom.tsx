/** 学习室：展示原理和真实来源，以用户明确回答触发讲评，真实任务状态驱动等待界面。 */
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiFailure } from '../../api/client';
import { archiveLearning, cancelLearningJob, readLearning, readLearningJob, sendLearningMessage } from '../../api/learning';
import type { LearningDetail, LearningJob, LearningTurn, SendLearningMessage } from '../../api/learning';
import { knownFailure, useWriteAction } from '../auth/shared';
import { LearningError, useLearningFailure } from './LearningPage';

const turnLabels: Record<LearningTurn['kind'], string> = { user_request: '我的学习请求', explanation: '原理讲解 · AI 整理', exercise: '应用练习 · AI 自编', user_response: '我的练习回答', feedback: '本次回答的反馈 · AI 分析' };
const stageLabels: Record<string, string> = { accepted: '请求已接收', understanding: '正在理解学习目标', retrieving: '正在读取所选知识', evaluating: '正在组织讲解或练习', validating: '正在核对内容与来源', composing: '正在保存学习内容' };
/** job为实际任务，只有服务器终态才允许下一次提交。 */
function active(job: LearningJob | null) { return !!job && ['queued', 'running', 'cancel_requested'].includes(job.status); }
/** id为本人学习会话；草稿只驻留组件，隐藏或退出时由上层销毁。 */
export function LearningRoom({ id }: { id: string }) {
  const fail = useLearningFailure(), write = useWriteAction(), cancel = useWriteAction();
  const [detail, setDetail] = useState<LearningDetail | null>(null), [job, setJob] = useState<LearningJob | null>(null);
  const [refresh, setRefresh] = useState(0), [loading, setLoading] = useState(false), [error, setError] = useState<ApiFailure | null>(null);
  const [draft, setDraft] = useState(''), [mode, setMode] = useState<SendLearningMessage['mode']>('explain'), [exercise, setExercise] = useState('');
  const pageRequest = useRef<AbortController | null>(null), form = useRef<HTMLTextAreaElement | null>(null);
  const receipt = useRef<{ digest: string; key: string; data: SendLearningMessage } | null>(null);
  /** value为请求错误；失权销毁全页，其余保留草稿让用户重读或同体重试。 */
  function reject(value: unknown) { const safe = knownFailure(value); if (safe.status === 401 || safe.status === 404) fail(safe); else setError(safe); }
  useEffect(() => {
    const request = new AbortController(); pageRequest.current?.abort(); setLoading(true);
    readLearning(id, undefined, request.signal).then(value => { if (!request.signal.aborted) { setDetail(value); setJob(value.active_job); setError(null); setLoading(false); } })
      .catch(error => { if (!request.signal.aborted) { const safe = knownFailure(error); if (safe.status === 401 || safe.status === 404) fail(safe); else setError(safe); setLoading(false); } });
    return () => { request.abort(); pageRequest.current?.abort(); };
  }, [id, refresh, fail]);
  const jobId = active(job) ? job!.id : undefined;
  useEffect(() => {
    if (!jobId) return;
    const request = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    /** 无参数；每次真实GET结束后再等待，不叠加请求，不发送假阶段。 */
    async function poll() {
      try {
        const value = await readLearningJob(id, jobId!, request.signal);
        if (request.signal.aborted) return;
        setError(null);
        if (active(value)) { setJob(value); timer = setTimeout(poll, 2000); }
        else { const latest = await readLearning(id, undefined, request.signal); if (!request.signal.aborted) { setDetail(latest); setJob(latest.active_job ?? value); } }
      } catch (error) { if (!request.signal.aborted) { const safe = knownFailure(error); if (safe.status === 401 || safe.status === 404) fail(safe); else setError(safe); } }
    }
    timer = setTimeout(poll, 800);
    return () => { request.abort(); clearTimeout(timer); };
  }, [id, jobId, fail]);
  /** 无参数；读取后续已发布回合，避免旧分页晚响应混入新修订。 */
  function more() {
    if (!detail?.next_cursor || loading) return;
    pageRequest.current?.abort(); const request = new AbortController(); pageRequest.current = request; const before = detail; setLoading(true);
    readLearning(id, detail.next_cursor, request.signal).then(value => {
      if (request.signal.aborted) return;
      if (value.session.revision !== before.session.revision) { setRefresh(value => value + 1); return; }
      setDetail(current => current === before ? { ...value, items: [...before.items, ...value.items.filter(item => !before.items.some(existing => existing.id === item.id))] } : current); setLoading(false);
    }).catch(error => { if (!request.signal.aborted) { reject(error); setLoading(false); } });
  }
  /** 无参数；原始回答绑定明确练习，结果未知重试复用原请求ID与幂等键。 */
  function send() {
    if (!detail || active(job) || !draft.trim() || mode === 'respond' && !exercise) return;
    const base = { content: draft, expected_revision: detail.session.revision, mode, ...(mode === 'respond' ? { responds_to_turn_id: exercise } : {}) };
    const digest = JSON.stringify(base);
    if (receipt.current?.digest !== digest) receipt.current = { digest, key: crypto.randomUUID(), data: { ...base, client_message_id: crypto.randomUUID() } };
    const sent = receipt.current;
    void write.run(signal => sendLearningMessage(id, sent.data, sent.key, signal), result => {
      receipt.current = null; setDraft(''); setError(null); setDetail(value => value && { ...value, session: { ...value.session, revision: result.revision } });
      setJob({ id: result.job_id, learning_session_id: id, run_id: result.run_id, status: 'queued', stage: 'accepted', error_code: null, started_at: null, finished_at: null });
    }, reject);
  }
  /** next/text/exerciseId来自明确按钮；只填草稿，不自动调用模型或丢弃已有输入。 */
  function prepare(next: SendLearningMessage['mode'], text: string, exerciseId = '') { setMode(next); setExercise(exerciseId); setDraft(value => value || text); form.current?.focus(); }
  const busy = write.pending || write.seconds > 0 || active(job) || loading;
  if (!detail) return <><Link to="/app/learning">← 我的学习</Link><p role="status">正在读取学习内容…</p><LearningError error={error} />{error && <button type="button" onClick={() => setRefresh(value => value + 1)}>重新读取</button>}</>;
  const { session, basis_cards: cards } = detail, exercises = detail.items.filter(item => item.kind === 'exercise');
  return <><Link to="/app/learning">← 我的学习</Link><header className="reading-heading"><p className="section-label">{session.status === 'archived' ? '已归档 · 可回看' : '独立学习 · 从原理到应用'}</p><h1>{session.title}</h1><p>{session.goal}</p></header>
    <div className="learning-room-grid"><aside className="learning-sources" aria-label="本次学习的书与知识"><p className="section-label">本次选用的知识</p><h2>{cards.length} 张卡片，逐一可追溯</h2><p className="reading-muted">这是本次选择的范围，不代表调用了整个书库。具体讲解的依据标在对应段落下。</p>
      {cards.map(card => <details key={card.card_id}><summary>{card.title}</summary><p>《{card.book.title}》 · {card.book.author_display ?? '作者待核实'}</p><p>{card.statement}</p><Link to={`/app/library/${session.release_id}/cards/${encodeURIComponent(card.card_id)}`} target="_blank" rel="noopener noreferrer">打开完整原理与来源 ↗</Link></details>)}
    </aside><section className="learning-dialogue" aria-label="学习内容">
      {!detail.items.length && <div className="learning-welcome"><p className="section-label">目标已保存</p><h2>先把原理讲透，再试着用一次。</h2><p>你可以先让 AI 解释来龙去脉，也可以提出自己的困惑。这里不会仅凭阅读就给出“已掌握”的评价。</p></div>}
      {detail.items.map(item => <article key={item.id} className={`learning-turn learning-turn-${item.kind}`} id={`turn-${item.id}`}><p className="section-label">{turnLabels[item.kind]}</p><div className="learning-prose">{item.content.text}</div>
        {item.content.sections.map((section, index) => <section key={index}><h3>{section.title}</h3><div className="learning-prose">{section.body}</div>{section.basis_card_ids.length > 0 && <ul className="learning-citations" aria-label="本段知识依据">{section.basis_card_ids.map(id => { const card = cards.find(card => card.card_id === id); return card ? <li key={id}><Link to={`/app/library/${session.release_id}/cards/${encodeURIComponent(id)}`} target="_blank" rel="noopener noreferrer">{card.title} ·《{card.book.title}》· {card.book.author_display ?? '作者待核实'} ↗</Link></li> : null; })}</ul>}</section>)}
        {item.kind === 'exercise' && session.status === 'active' && <button type="button" className="secondary-action" disabled={busy} onClick={() => prepare('respond', '', item.id)}>回答这道练习</button>}
        {item.kind === 'feedback' && item.responds_to_turn_id && <p className="reading-muted">针对这一次实际回答的反馈，不代表对长期掌握程度的认证。{detail.items.some(turn => turn.id === item.responds_to_turn_id) && <a href={`#turn-${item.responds_to_turn_id}`}>回看我的回答</a>}</p>}
      </article>)}
      {detail.next_cursor && <button type="button" disabled={loading} onClick={more}>读取后续学习内容</button>}
      {job && <section className="learning-job" aria-label="学习任务"><p role="status">{active(job) ? stageLabels[job.stage] : job.status === 'succeeded' ? '本次内容已保存。' : job.status === 'cancelled' ? '本次任务已取消，已保存的原文仍在。' : job.error_code === 'MODEL_UNAVAILABLE' ? '模型尚未配置，本次未生成内容。' : '本次生成未完成，没有发布未验证的内容。'}</p>{active(job) && <button type="button" className="text-action" disabled={cancel.pending || cancel.seconds > 0 || job.status === 'cancel_requested'} onClick={() => void cancel.run(signal => cancelLearningJob(id, job.id, signal), setJob, reject)}>{job.status === 'cancel_requested' ? '正在取消…' : '取消本次生成'}</button>}</section>}
      <LearningError error={error ?? write.failure ?? cancel.failure} />
      <div className="learning-toolbar"><button type="button" className="text-action" disabled={loading || write.pending || cancel.pending} onClick={() => { setError(null); setRefresh(value => value + 1); }}>重新读取记录（保留输入）</button>{session.status === 'active' && <button type="button" className="text-action" disabled={busy || !!draft} onClick={() => void write.run(signal => archiveLearning(id, session.revision, signal), result => setDetail(value => value && { ...value, session: result }), reject)}>归档这次学习</button>}</div>
      {session.status === 'active' ? <form className="learning-composer" onSubmit={event => { event.preventDefault(); send(); }}><h2>继续和 AI 深入</h2><p>先选接下来要做的事，再写下你的问题或回答。确认发送后才调用 AI。</p>
        <div className="learning-toolbar"><button type="button" className="secondary-action" disabled={busy} onClick={() => prepare('explain', '请结合我选的知识卡，把原理的来龙去脉、适用边界和应用方式讲清楚。区分书中的观点与 AI 的延伸解释。')}>深入解释原理</button><button type="button" className="secondary-action" disabled={busy} onClick={() => prepare('practice', '请围绕我选的知识和学习目标，设计一道可应用的练习。先不要给参考答案，等我回答后再具体反馈。')}>出一道应用练习</button></div>
        <label>本次交流方式<select value={mode} disabled={busy} onChange={event => { setMode(event.target.value as SendLearningMessage['mode']); setExercise(''); }}><option value="explain">讲解原理 / 继续追问</option><option value="practice">生成应用练习</option><option value="respond" disabled={!exercises.length}>提交练习回答</option></select></label>
        {mode === 'respond' && <label>回答哪道练习<select value={exercise} required disabled={busy} onChange={event => setExercise(event.target.value)}><option value="">请选择已生成的练习</option>{exercises.map((item, index) => <option key={item.id} value={item.id}>练习 {index + 1}：{item.content.text.slice(0, 55)}</option>)}</select></label>}
        <label>{mode === 'respond' ? '我的练习回答' : '想和 AI 继续聊的内容'}<textarea ref={form} value={draft} onChange={event => setDraft(event.target.value)} disabled={write.pending} rows={6} maxLength={20000} required placeholder={mode === 'respond' ? '写下你的判断、依据和不确定的地方，不必追求标准答案。' : '哪里还不明白？想换个例子，还是结合自己的情境继续讨论？'} /></label>
        <button type="submit" disabled={busy || !draft.trim() || mode === 'respond' && !exercise || write.failure?.status === 409 && error?.status === 409}>{write.pending ? '正在提交…' : '发送，继续和 AI 学习'}</button>{write.seconds > 0 && <p role="status">{write.seconds} 秒后可重试</p>}<p className="reading-muted">未配置模型时会明确提示失败，不用演示内容替代真实讲解。</p>
      </form> : <section className="reading-empty"><h2>学习记录已归档</h2><p>已保存内容保留供回看。想探索新方向，可以选择新的知识卡。</p><Link to="/app/learning/new">开始新的学习</Link></section>}
    </section></div>
  </>;
}
