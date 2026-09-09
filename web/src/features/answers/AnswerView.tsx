/** 已发布的结构化答案；建议在前、来源可追溯，续聊仅交还可编辑草稿。 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { readAnswer } from '../../api/answers';
import type { Answer } from '../../api/answers';
import { ApiFailure } from '../../api/client';
import { readJob } from '../../api/runs';
import type { Run } from '../../api/runs';
import { knownFailure } from '../auth/shared';
import { useProblemFailure } from '../problems/ProblemPage';
import { SaveActionControl, AnswerFeedback } from '../personal/PersonalControls';
import '../../styles/answers.css';

const confidence = { high: '高', medium: '中', low: '低' };
const claimTypes = { author_claim: '作者观点', quoted_other: '书中转引他人观点', system_inference: '系统推断', unclassified: '来源归属未分类' };
const relationTypes = { support: '支持', attack: '反驳', contradict: '矛盾', undercut: '削弱依据', complement: '补充', depend_on: '依赖' };
const synthesisTypes = { cross_book_synthesis: '跨书综合', extension: '延伸', hypothesis: '假设', analogy: '类比', new_option: '新选项' };
const seats = [['support', '支持席'], ['opposition', '反对席'], ['alternative', '替代方案席'], ['evidence_audit', '证据审查席']] as const;
/** values为完整条目；空值明确显示尚无该项。 */
function Items({ values, empty = '本次未提供' }: { values: string[]; empty?: string }) { return values.length ? <ul>{values.map((value, index) => <li key={index}>{value}</li>)}</ul> : <p className="reading-muted">{empty}</p>; }
/** ids是答案公开卡片ID；链接进入既有授权知识库阅读边界。 */
function CardLinks({ ids, answer }: { ids: string[]; answer: Answer }) {
  return ids.length ? <div className="answer-card-links">{ids.map((id, index) => <Link key={`${id}-${index}`} to={`/app/library/${answer.release_id}/cards/${encodeURIComponent(id)}`}>查看知识卡 {index + 1}<span className="answer-card-id"> · {id}</span></Link>)}</div> : null;
}
/** answer是已验证归属的公开答案；onContinue只填入聊天框，disabled表示档案不可写。dev预览也复用此纯渲染组件。 */
export function AnswerBody({ answer, onContinue, disabled }: { answer: Answer; onContinue: (prompt: string) => void; disabled: boolean }) {
  const fail = useProblemFailure();
  const content = answer.content, verdict = content.verdict;
  /** ids为本次检索书号，保留没有公开书名的真实标识。 */
  const bookNames = (ids: string[]) => ids.map(id => content.books.find(book => book.book_id === id)?.title ?? id);
  return <article className="answer-reader" aria-label="已发布答案">
    <header className="answer-header"><p className="section-label">这次分析 · 输入修订 {answer.input_revision}</p><span className="stamp-seal" aria-hidden="true">有出处<br />可追溯</span><h2>先看建议</h2><p className="answer-conclusion">{verdict.conclusion}</p><p>{verdict.reasoning_summary}</p><p className="reading-muted">判断把握：{confidence[verdict.confidence]} · {answer.validation_status === 'semantic_reviewed' ? '已进行语义复核' : '结构校验已通过，尚不代表语义准确'}</p><CardLinks ids={verdict.basis_card_ids} answer={answer} /></header>
    <section aria-label="行动建议"><h3>可以怎样行动</h3>{content.actions.length ? <ol className="answer-actions">{content.actions.map((action, index) => <li key={index}><h4>{action.step}</h4><dl><dt>完成标准</dt><dd>{action.completion_criteria}</dd><dt>观察信号</dt><dd>{action.validation_signal}</dd><dt>停止条件</dt><dd>{action.stop_condition}</dd></dl><CardLinks ids={action.basis_card_ids} answer={answer} /><SaveActionControl key={`${answer.id}/${index}`} answer={answer.id} index={index} disabled={disabled} onFailure={fail} /></li>)}</ol> : <p>本次未给出可执行行动。</p>}</section>
    <AnswerFeedback key={answer.id} answer={answer.id} onFailure={fail} />
    {content.system_syntheses.length > 0 && <section aria-label="系统综合"><h3>系统综合</h3><p className="reading-muted">以下内容是系统基于知识提出的综合与延伸。</p>{content.system_syntheses.map((item, index) => <div className="answer-inset" key={index}><h4>{item.title}</h4><p className="answer-tag">系统综合 · {synthesisTypes[item.type]} · 把握 {confidence[item.confidence]}</p><p>{item.content}</p><p>需要验证：{item.validation_needed}</p><CardLinks ids={item.basis_card_ids} answer={answer} /></div>)}</section>}
    <section aria-label="问题理解"><h3>这次如何理解你的问题</h3><p>{content.problem_framing.reframed_question}</p><p>{content.problem_framing.diagnostic_summary}</p><details><summary>查看原问题、假设与未知</summary><p>{content.problem_framing.surface_question}</p><h4>隐含假设</h4><Items values={content.problem_framing.hidden_assumptions} /><h4>关键未知</h4><Items values={content.problem_framing.key_uncertainties} /></details></section>
    <section aria-label="参考书目"><h3>本次参考书目</h3><ul className="answer-books">{content.books.map(book => <li key={book.book_id}><strong>{book.title}</strong><span>{book.author_display ?? '作者信息未提供'}</span></li>)}</ul><details><summary>查看检索覆盖与采用范围</summary><p>检索涉及 {content.call_ledger.books_searched.length} 本书；出现候选 {content.call_ledger.books_with_candidates.length} 本书；实际采用 {content.call_ledger.admitted.length} 张卡片。</p><h4>检索涉及</h4><Items values={bookNames(content.call_ledger.books_searched)} /><h4>出现候选</h4><Items values={bookNames(content.call_ledger.books_with_candidates)} /><h4>实际采用卡片</h4><CardLinks ids={content.call_ledger.admitted} answer={answer} /><h4>检索问题</h4><Items values={content.call_ledger.queries} />{content.call_ledger.retrieval_degraded && <p className="answer-gap">本次检索已降级，覆盖可能不足。</p>}</details></section>
    <section aria-label="采用的知识与原理"><h3>这些建议背后的知识</h3>{content.witness_cards.map((card, index) => <article className="answer-witness" key={card.card_id}><p className="section-label">知识 {index + 1} · {card.book_title} · {card.author ?? '作者信息未提供'}</p><h4>{card.adopted_claim}</h4><p className="answer-tag">{claimTypes[card.source_claim_type]} · 把握 {confidence[card.confidence]}</p><h5>原理</h5><p>{card.principle}</p>{(card.principle_gap || card.source_gap) && <p className="answer-gap">{card.principle_gap ? '原理说明存在缺口。' : ''}{card.source_gap ? '来源证据存在缺口。' : ''}</p>}<details><summary>展开机制、情境映射与使用边界</summary><h5>为什么会起作用</h5><p>{card.mechanism}</p><h5>如何对应你的处境</h5><p>{card.situation_mapping}</p><h5>独立判断</h5><p>{card.independent_judgment}</p><h5>对建议的实际影响</h5><p>{card.judgment_effect}</p><h5>成立假设</h5><Items values={card.assumptions} /><h5>不适用条件</h5><Items values={card.non_applicable_conditions} /><h5>误用风险</h5><Items values={card.misuse_risks} /><h5>本次未采用的范围</h5><Items values={card.excluded_scope} /><p>章节：{card.chapters.join('、') || '未提供'}</p>{card.quote ? <div><h5>本次短引</h5><blockquote>{card.quote.text}</blockquote></div> : <p className="reading-muted">此卡当前无可显示短引，请查看下方来源状态。</p>}</details><CardLinks ids={[card.card_id]} answer={answer} /></article>)}</section>
    <section aria-label="观点圆桌"><h3>把不同意见放在一起看</h3><div className="answer-seats">{seats.map(([key, label]) => <section className="answer-seat" key={key}><h4>{label}</h4><p className="answer-tag">{content.roundtable[key].status === 'gap' ? '席位缺口 · 尚无充分代表' : '已有观点代表'}</p><p>{content.roundtable[key].claim}</p><CardLinks ids={content.roundtable[key].card_ids} answer={answer} /></section>)}</div><details><summary>查看论证关系与成立条件</summary>{content.argument_relations.length ? content.argument_relations.map((relation, index) => <div className="answer-inset" key={index}><h4>{relationTypes[relation.type]}：{relation.to_claim}</h4><p>{relation.explanation}</p><p>成立条件：{relation.condition || '本次未提供'}</p><CardLinks ids={relation.from_card_ids} answer={answer} /></div>) : <p>本次未提供论证关系。</p>}</details><div className="answer-seats"><section><h4>共识</h4><Items values={verdict.consensus} /></section><section><h4>分歧</h4><Items values={verdict.disagreements} /></section><section><h4>仍不确定</h4><Items values={verdict.uncertainties} /></section><section><h4>什么会改变结论</h4><Items values={verdict.change_conditions} /></section></div></section>
    <section aria-label="来源与短引"><h3>回到来源</h3>{content.sources.map((source, index) => <div className="answer-source" key={`${source.evidence_id}-${index}`}><h4>{source.book_title} · {source.author ?? '作者信息未提供'}</h4><p className="reading-muted">章节：{source.chapter || '未提供'} · 证据 {source.evidence_id}</p>{source.quote_available && source.excerpt !== null ? <div><p className="reading-muted">来源预览</p><blockquote>{source.excerpt}</blockquote></div> : <p className="answer-gap">当前没有可显示的原文短引，可能受引用权限限制；不补写原文。</p>}<CardLinks ids={source.card_ids} answer={answer} /></div>)}</section>
    {(content.knowledge_groups.length > 0 || content.learning_takeaways.length > 0) && <section aria-label="可复用的知识"><h3>把这次思考留下来</h3>{content.knowledge_groups.map((group, index) => <details key={index}><summary>{group.title}</summary><p>{group.purpose}</p><p>{group.synthesis}</p><h4>待解问题</h4><Items values={group.open_questions} /><CardLinks ids={group.card_ids} answer={answer} /></details>)}{content.learning_takeaways.map((takeaway, index) => <div className="answer-inset" key={index}><h4>{takeaway.method}</h4><p>{takeaway.how_to_reuse}</p><CardLinks ids={takeaway.basis_card_ids} answer={answer} /></div>)}</section>}
    <section className="answer-continuation" aria-label="继续这次讨论"><h3>下一步，继续聊什么</h3>{content.continuation_options.map((option, index) => <div key={index}><h4>{option.title}</h4><p>{option.description}</p><p>{option.next_move}</p></div>)}<p>{content.next_chat_action.reason}</p><p className="reading-muted">点击后填入可编辑输入框，由你确认发送；本次点击不会启动分析。</p><p className="answer-next-prompt">{content.next_chat_action.prompt}</p><button type="button" disabled={disabled} onClick={() => onContinue(content.next_chat_action.prompt)}>把这个问题带回对话</button></section>
  </article>;
}
/** run已完成且结果为答案；releaseId限定知识版本，身份变化由父边界卸载。 */
export function AnswerView({ run, releaseId, onContinue, disabled = false }: { run: Run; releaseId: string; onContinue: (prompt: string) => void; disabled?: boolean }) {
  const fail = useProblemFailure(), [answer, setAnswer] = useState<Answer | null>(null), [failure, setFailure] = useState<ApiFailure | null>(null), [attempt, setAttempt] = useState(0);
  const { id, job_id: jobId, problem_id: problemId, input_revision: inputRevision } = run;
  useEffect(() => {
    const request = new AbortController(); setAnswer(null); setFailure(null);
    /** 无参数；先核对实际job，再取该job发布的答案，整个链路只有GET。 */
    async function load() {
      try {
        const job = await readJob(jobId, request.signal, { problemId, runId: id });
        if (request.signal.aborted) return;
        if (job.status !== 'succeeded' || !job.result_ref) throw new ApiFailure('INVALID_RESPONSE');
        const value = await readAnswer(job.result_ref, { problemId, runId: id, releaseId, inputRevision }, request.signal);
        if (!request.signal.aborted) setAnswer(value);
      } catch (error) { if (!request.signal.aborted) { const safe = knownFailure(error); setAnswer(null); if (safe.status === 401 || safe.status === 404) fail(safe); else setFailure(safe); } }
    }
    void load(); return () => request.abort();
  }, [id, jobId, problemId, releaseId, inputRevision, attempt, fail]);
  if (failure) return <section className="answer-reader" aria-label="答案读取失败"><p role="alert">暂时无法读取已发布答案，草稿仍然保留。</p><button className="secondary-action" type="button" onClick={() => setAttempt(value => value + 1)}>重新读取答案</button></section>;
  if (!answer || answer.run_id !== id || answer.problem_id !== problemId || answer.release_id !== releaseId || answer.input_revision !== inputRevision) return <p role="status">正在读取已发布答案…</p>;
  return <AnswerBody answer={answer} onContinue={onContinue} disabled={disabled} />;
}
