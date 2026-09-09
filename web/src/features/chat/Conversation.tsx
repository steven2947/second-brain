import { characterImage, useCharacter } from '../journal/character';
/** 真实消息与异步任务界面；服务端消息、修订和任务状态为事实源。 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiFailure } from '../../api/client';
import { readProblem } from '../../api/problems';
import type { Problem } from '../../api/problems';
import { cancelJob, listMessages, readRun, sendMessage, startAnalysis } from '../../api/runs';
import type { AcceptedRun, Message, Run, SendMessage } from '../../api/runs';
import { knownFailure, useWriteAction } from '../auth/shared';
import { useProblemFailure } from '../problems/ProblemPage';
import { AnswerView } from '../answers/AnswerView';
import '../../styles/chat.css';

const stages: Record<Run['stage'], string> = { accepted: '已接收', understanding: '理解问题', retrieving: '检索知识', evaluating: '评估观点', validating: '核验证据', composing: '组织表达' };
const stageOrder: Run['stage'][] = ['understanding', 'retrieving', 'evaluating', 'validating', 'composing'];
const statuses: Record<Run['status'], string> = { queued: '排队中', running: '处理中', cancel_requested: '已请求取消，等待任务停止', succeeded: '已完成', failed: '未完成', cancelled: '已取消' };
/** run为真实任务；只从后端终态判断是否停止读取。 */
function terminal(run: Run) { return run.status === 'succeeded' || run.status === 'failed' || run.status === 'cancelled'; }
/** error为受控错误；不呈现服务端自由文本或宣称写入成功。 */
function failureText(error: ApiFailure) {
  if (error.status === 409) return '背景或问题状态已变化。草稿已保留，请读取最新背景，核对后再明确发送。';
  if (error.status === 429 && error.code === 'QUOTA_EXCEEDED') return '本月分析额度已用完，请查看账号额度。草稿已保留。';
  if (error.status === 429) return '请求过于频繁，请等待后手动重试。';
  return '暂时无法确认请求结果。草稿已保留；相同内容再次发送会复用本次编号，不会自动重发。';
}
/** run为服务端结果，revision为最新已读档案修订；不把完成状态冒充正式答案。 */
function resultText(run: Run, revision: number) {
  // 成功发布追问本身会增加一版档案，不把这次合法写回误认为用户补充了新背景。
  const publishedRevision = run.input_revision + (run.status === 'succeeded' ? 1 : 0);
  if (run.stale || run.error_code === 'RUN_STALE' || publishedRevision < revision) return '背景已有更新，这次任务对应旧背景。请核对最新背景，再主动点击直接分析。';
  if (run.error_code === 'MODEL_UNAVAILABLE') return '模型尚未配置，消息已保存';
  if (run.error_code === 'ANALYSIS_UNAVAILABLE') return '正式答案服务正在接入，消息已保存';
  if (run.status === 'cancelled') return '任务已停止，已经保存的消息仍然保留。';
  if (run.status === 'failed') return '这次任务未完成，已保存的消息仍然保留。你可以核对背景后主动发起新的分析。';
  if (run.status === 'succeeded') return run.outcome === 'question' ? '追问已生成，请在对话记录中查看。' : run.outcome === 'answer' ? '答案已发布，正在读取本次任务对应的内容。' : run.outcome === 'coverage_gap' ? '当前知识覆盖不足，本次未发布正式答案。请查看对话中的覆盖说明。' : '本次任务已结束，请查看对话中的实际说明。';
  return '仅显示服务端当前状态；接收消息不代表已经生成答案。';
}

/** problem为已验证本人档案；onRevision同步消息修订，onProblem更新最新详情而保留输入。 */
export function Conversation({ problem, onRevision, onProblem, initialDraft = '', onDraftUsed }: {
  problem: Problem;
  onRevision: (revision: number, available: boolean) => void;
  onProblem: (value: Problem) => void;
  initialDraft?: string;
  onDraftUsed?: () => void;
}) {
  const fail = useProblemFailure(), action = useWriteAction();
  const [draft, setDraft] = useState(initialDraft), [intent, setIntent] = useState<SendMessage['intent']>(problem.clarification.pending_question ? 'answer' : 'supplement');
  useEffect(() => { if (initialDraft) onDraftUsed?.(); }, [initialDraft, onDraftUsed]);
  const [messages, setMessages] = useState<Message[]>([]), [cursor, setCursor] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false), [reading, setReading] = useState(false), [available, setAvailable] = useState(problem.library_available);
  const [readFailure, setReadFailure] = useState<ApiFailure | null>(null), [conflict, setConflict] = useState(false), [notice, setNotice] = useState('');
  const [selected, setSelected] = useState<{ id: string; jobId?: string; historical?: boolean } | null>(null), [run, setRun] = useState<Run | null>(null), [pollAttempt, setPollAttempt] = useState(0);
  const [readDeadline, setReadDeadline] = useState(0), [now, setNow] = useState(Date.now());
  const reads = useRef<AbortController | null>(null), mounted = useRef(true), pageCount = useRef(1), items = useRef<Message[]>([]);
  const explicitRun = useRef(false), latest = useRef(problem), composing = useRef(false);
  const submission = useRef<{ signature: string; revision: number; key: string; clientId: string } | null>(null);
  const analysis = useRef<{ revision: number; key: string } | null>(null);
  latest.current = problem;
  const id = problem.id, count = Array.from(draft).length, readSeconds = Math.max(0, Math.ceil((readDeadline - now) / 1000));
  const allowed = problem.library_available && available;

  /** error为读取失败；身份失效立即交给父边界，其余停止并等待手动读取。 */
  const rejectedRead = useCallback((error: unknown) => {
    const safe = knownFailure(error);
    if (safe.status === 401 || safe.status === 404) { fail(safe); return; }
    setReadFailure(safe);
    if (safe.status === 429) { setNow(Date.now()); setReadDeadline(Date.now() + Math.max(1, safe.retryAfter ?? 30) * 1000); }
  }, [fail]);
  useEffect(() => {
    if (!readSeconds) return;
    const timer = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, [readSeconds]);

  /** next选择下一页；refreshDetail显式或终态重读档案，signal绑定调用者的取消周期。 */
  const loadMessages = useCallback(async (next?: string, refreshDetail = false, signal?: AbortSignal) => {
    reads.current?.abort(); const request = new AbortController(); reads.current = request;
    /** 无参数；上层任务取消时同时取消消息读取。 */
    const abort = () => request.abort();
    signal?.addEventListener('abort', abort, { once: true });
    if (signal?.aborted) request.abort();
    setReading(true);
    try {
      if (refreshDetail) {
        const value = await readProblem(id, request.signal);
        if (request.signal.aborted) return false;
        onProblem(value); if (value.revision >= latest.current.revision) latest.current = value;
      }
      let combined = next ? items.current : [];
      let page = await listMessages(id, next, request.signal);
      const targetPages = next ? 1 : pageCount.current;
      let pages = 1;
      for (;;) {
        if (!page.library_available) combined = combined.filter(item => item.role === 'user');
        const previous = combined.at(-1)?.sequence ?? 0;
        if (page.items.some(item => item.sequence <= previous || combined.some(old => old.id === item.id))) throw new ApiFailure('INVALID_RESPONSE');
        combined = [...combined, ...page.items];
        if (!page.next_cursor || pages >= targetPages) break;
        page = await listMessages(id, page.next_cursor, request.signal); pages += 1;
      }
      if (request.signal.aborted) return false;
      items.current = combined; pageCount.current = next ? pageCount.current + 1 : pages;
      setMessages(combined); setCursor(page.next_cursor); setAvailable(page.library_available); setLoaded(true); setReadFailure(null);
      onRevision(page.revision, page.library_available);
      latest.current = { ...latest.current, revision: Math.max(latest.current.revision, page.revision), library_available: page.library_available };
      if (!page.library_available) { setSelected(null); setRun(null); }
      else if (!explicitRun.current && !page.next_cursor) {
        const last = combined.filter(item => item.role === 'user').at(-1);
        if (last?.run_id) setSelected(current => current?.id === last.run_id ? current : { id: last.run_id! });
      }
      if (refreshDetail) setConflict(false);
      return true;
    } catch (error) { if (!request.signal.aborted) rejectedRead(error); return false; }
    finally { signal?.removeEventListener('abort', abort); if (!request.signal.aborted && mounted.current) setReading(false); }
  }, [id, onProblem, onRevision, rejectedRead]);

  useEffect(() => {
    mounted.current = true; void loadMessages();
    return () => { mounted.current = false; reads.current?.abort(); };
  }, [loadMessages]);

  useEffect(() => {
    if (!selected || !allowed) return;
    const request = new AbortController(); let timer: number | undefined;
    /** 无参数；每次先读取实际档案，再读取关联任务，终态后停止。 */
    async function poll() {
      try {
        const current = await readProblem(id, request.signal);
        if (request.signal.aborted) return;
        onProblem(current); if (current.revision >= latest.current.revision) latest.current = current;
        if (!current.library_available) { setAvailable(false); setRun(null); await loadMessages(undefined, false, request.signal); return; }
        const value = await readRun(selected!.id, request.signal, id);
        if (request.signal.aborted) return;
        if (selected!.jobId && selected!.jobId !== value.job_id) throw new ApiFailure('INVALID_RESPONSE');
        setRun(value); setReadFailure(null);
        if (terminal(value)) await loadMessages(undefined, true, request.signal);
        else timer = window.setTimeout(() => { void poll(); }, 2000);
      } catch (error) { if (!request.signal.aborted) rejectedRead(error); }
    }
    void poll();
    return () => { request.abort(); window.clearTimeout(timer); };
  }, [id, selected, pollAttempt, allowed, onProblem, loadMessages, rejectedRead]);

  /** value为真实202凭据；sent只清除本次已发送原文，草稿后续修改保留。 */
  function accepted(value: AcceptedRun, sent?: string) {
    explicitRun.current = true; setRun(null); setSelected({ id: value.run_id, jobId: value.job_id });
    latest.current = { ...latest.current, revision: Math.max(latest.current.revision, value.revision) };
    submission.current = null; analysis.current = null;
    onRevision(value.revision, true); setConflict(false);
    if (sent !== undefined) setDraft(current => current === sent ? '' : current);
    setNotice(sent !== undefined ? '消息已保存，任务已接收。' : '直接分析请求已保存，任务已接收。');
    void loadMessages();
  }
  /** error为单次写失败；冲突必须手动读取后再由用户提交。 */
  function rejectedWrite(error: ApiFailure) { if (error.status === 401 || error.status === 404) fail(error); else if (error.status === 409) setConflict(true); }
  /** direct为用户明确直接分析意图；有草稿时一并原样提交，没有草稿才走独立分析端点。 */
  function submit(direct = false) {
    if (composing.current || action.pending || action.seconds || reading || conflict || !allowed || problem.status === 'archived' || count > 20000) return;
    const revision = latest.current.revision; setNotice('');
    if (draft.trim()) {
      const data = { content: draft, intent: direct ? 'analyze_now' as const : intent };
      const signature = JSON.stringify(data);
      if (submission.current?.signature !== signature) submission.current = { signature, revision, key: crypto.randomUUID(), clientId: crypto.randomUUID() };
      const current = submission.current;
      void action.run(signal => sendMessage(id, { ...data, expected_revision: current.revision, client_message_id: current.clientId }, current.key, signal), value => accepted(value, data.content), rejectedWrite);
    } else if (direct) {
      if (!analysis.current) analysis.current = { revision, key: crypto.randomUUID() };
      const current = analysis.current;
      void action.run(signal => startAnalysis(id, { expected_revision: current.revision }, current.key, signal), value => accepted(value), rejectedWrite);
    }
  }
  /** 无参数；真实取消响应决定状态，cancel_requested继续等待终态。 */
  function cancel() {
    if (!run || terminal(run)) return;
    const current = run; setNotice('');
    void action.run(signal => cancelJob(current.job_id, signal, { problemId: id, runId: current.id }), job => {
      setRun(value => value?.id === current.id ? { ...value, status: job.status, stage: job.stage, error_code: job.error_code, finished_at: job.finished_at } : value);
      setNotice(job.status === 'cancelled' ? '任务已取消，消息仍然保留。' : job.status === 'cancel_requested' ? '取消请求已送达，等待任务停止。' : '任务已有结果，未将它改为取消成功。');
      setPollAttempt(value => value + 1);
    }, rejectedWrite);
  }
  /** 无参数；用户明确重读后恢复GET轮询，不重发任何POST。 */
  async function reload() {
    if (Date.now() < readDeadline || reading) return;
    const success = await loadMessages(undefined, true);
    if (mounted.current && success) {
      if (submission.current && submission.current.revision !== latest.current.revision) submission.current = null;
      if (analysis.current && analysis.current.revision !== latest.current.revision) analysis.current = null;
      setNotice('已读取最新背景，草稿仍然保留。请核对后再决定是否发送。');
      setPollAttempt(value => value + 1);
    }
  }
  /** prompt是答案明确给出的下一句；保留已有输入，只填入编辑框，绝不提交。 */
  function continueAnswer(prompt: string) {
    setDraft(current => current.length ? `${current}\n\n${prompt}` : prompt);
    setNotice('续聊问题已加入输入框，原有草稿已保留。请编辑核对后再发送。');
    document.getElementById('chat-draft')?.focus();
  }
  const [character] = useCharacter();
  const disabled = action.pending || action.seconds > 0 || reading || !loaded || conflict || problem.status === 'archived' || !allowed;
  const visibleMessages = allowed ? messages : messages.filter(message => message.role === 'user');
  return <section className="chat-section" aria-labelledby="conversation-title">
    <div className="chat-heading"><div><p className="section-label">把思考继续下去</p><h2 id="conversation-title">对话记录</h2></div><span className="reading-muted">你的原话会完整保存</span></div>
    {!loaded ? <p role="status">正在读取对话…</p> : !visibleMessages.length ? <div className="chat-empty"><img className="chat-empty-reader" src={characterImage("/journal/librarian-reading", character)} alt="" aria-hidden="true" /><p>还没有对话消息。</p><p>补充你的背景，或直接分析当前问题。没有提交请求时，不会启动任务。</p></div> : <ol className="chat-messages" aria-label="已保存的对话消息">{visibleMessages.map(message => <li key={message.id} className={`chat-message chat-message-${message.role}${message.kind === 'clarification' ? ' chat-message-clarification' : ''}`}><span className="chat-speaker">{message.role === 'user' ? '你' : 'AI'}</span><p>{message.content}</p>{message.kind === 'answer' && message.run_id && <button className="secondary-action" type="button" onClick={() => { explicitRun.current = true; setRun(null); setSelected({ id: message.run_id!, historical: true }); }}>查看这条消息的答案</button>}</li>)}</ol>}
    {cursor && <div className="chat-pagination"><button className="secondary-action" type="button" disabled={reading || readSeconds > 0} onClick={() => { void loadMessages(cursor); }}>加载后续消息</button><p className="reading-muted">还有后续消息。读到末页后，才能恢复最后一条已加载消息关联的任务。</p></div>}
    {allowed && selected && <section className="chat-task" aria-label="当前消息关联任务" aria-live="polite"><span className="journal-tape tape-stripe" aria-hidden="true"></span><p className="chat-task-label">{selected.historical ? '已选择的历史消息关联任务' : explicitRun.current ? '本次提交关联的任务' : '当前已加载消息关联的任务'}</p>
      {run ? <><div className="chat-task-line"><strong>{statuses[run.status]}</strong><span>{stages[run.stage]} · 输入修订 {run.input_revision}</span></div>{!terminal(run) && run.status !== 'cancel_requested' && <ul className="chat-stages" aria-hidden="true">{stageOrder.map(stage => <li key={stage} className={stage === run.stage ? 'stage-now' : stageOrder.indexOf(stage) < stageOrder.indexOf(run.stage) ? 'stage-done' : ''}>{stages[stage]}</li>)}</ul>}<p>{resultText(run, problem.revision)}</p>{!terminal(run) && run.status !== 'cancel_requested' && <button className="secondary-action" type="button" disabled={action.pending || action.seconds > 0} onClick={cancel}>取消任务</button>}{!terminal(run) && <img className="chat-task-reader" src={characterImage("/journal/librarian-magnify", character)} alt="" aria-hidden="true" />}</> : <p>任务编号已确认，正在读取实际状态…</p>}
    </section>}
    {readFailure && <div className="problem-notice" role="alert"><p>读取已暂停，请检查连接后手动重读。不会自动重发消息。</p>{readFailure.requestId && <small>请求编号：{readFailure.requestId}</small>}</div>}
    {(readFailure || conflict) && <button className="secondary-action" type="button" disabled={reading || readSeconds > 0 || action.pending || action.seconds > 0} onClick={() => { void reload(); }}>{readSeconds ? `${readSeconds} 秒后可重读` : '读取最新背景'}</button>}
    {allowed && run && run.id === selected?.id && run.status === 'succeeded' && run.outcome === 'answer' && !run.stale && <AnswerView key={`${id}:${run.id}`} run={run} releaseId={problem.release_id} onContinue={continueAnswer} disabled={problem.status === 'archived'} />}
    {problem.status === 'archived' ? <p className="problem-notice">问题已归档，恢复后可以继续发送消息。</p> : !allowed ? <p className="problem-notice">当前仅显示你本人的消息。知识集不可用，暂时不能发送或分析。</p> : <div className="chat-compose">
      <div className="reading-field"><label htmlFor="chat-draft">补充背景或回应追问</label><textarea id="chat-draft" rows={4} value={draft} onChange={event => setDraft(event.target.value)} onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }} aria-describedby="chat-count" autoComplete="off" placeholder="你现在最在意什么？也可以写下新的事实……" /><p id="chat-count" className="reading-muted">{count} / 20000 字符 · 回车换行。{count > 20000 ? ' 请缩短至 20000 字符以内。' : ''}</p></div>
      <div className="chat-controls"><div className="reading-field"><label htmlFor="chat-intent">这条消息的用途</label><select id="chat-intent" value={intent} disabled={action.pending} onChange={event => { const value = event.target.value; if (value === 'answer' || value === 'supplement' || value === 'unknown') setIntent(value); }}><option value="supplement">补充背景</option><option value="answer">回应追问</option><option value="unknown">暂不确定</option></select></div><div className="problem-actions"><button type="button" disabled={disabled || !draft.trim() || count > 20000} onClick={() => submit()}>发送消息</button><button className="secondary-action" type="button" disabled={disabled || count > 20000} onClick={() => submit(true)}>直接分析</button></div></div>
      <p className="reading-muted">直接分析会停止背景追问；输入框有文字时，会连同原文一起提交。</p>
    </div>}
    {action.pending && <p role="status">正在提交请求…</p>}{action.seconds > 0 && <p role="status">{action.seconds} 秒后可重试</p>}
    {action.failure && !notice && <div className="problem-notice" role="alert"><p>{failureText(action.failure)}</p>{action.failure.requestId && <small>请求编号：{action.failure.requestId}</small>}</div>}
    {notice && <p className="chat-notice" role="status">{notice}</p>}
  </section>;
}
