/** 已发布答案只读边界；逐字段投影公开契约，不让内部字段进入页面。 */
import type { components } from './generated';
import { ApiFailure, objectValue, requestJson } from './client';

export type Answer = components['schemas']['Answer'];
export type AnswerContent = Answer['content'];
export type AnswerContext = { problemId: string; runId: string; releaseId: string; inputRevision: number };
type Decoder<T> = (value: unknown) => T;
/** value为公开文本，保留原文及完整长度。 */
function text(value: unknown): string { if (typeof value !== 'string') throw new Error('Invalid text'); return value; }
/** value为布尔字段，禁止隐式转换。 */
function bool(value: unknown): boolean { if (typeof value !== 'boolean') throw new Error('Invalid boolean'); return value; }
/** value为非负整数修订或索引。 */
function integer(value: unknown): number { if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) throw new Error('Invalid integer'); return value; }
/** value为完整UUID，路径不得包含任意字符串。 */
function uuid(value: unknown): string { const result = text(value); if (!/^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(result)) throw new ApiFailure('INVALID_REQUEST'); return result.toLowerCase(); }
/** decode指定非空值如何读取。 */
function nullable<T>(decode: Decoder<T>): Decoder<T | null> { return value => value === null ? null : decode(value); }
/** decode指定数组中每一项的公开字段。 */
function array<T>(decode: Decoder<T>): Decoder<T[]> { return value => { if (!Array.isArray(value)) throw new Error('Invalid array'); return value.map(decode); }; }
/** values为契约允许的枚举值。 */
function choice<const T extends readonly string[]>(...values: T): Decoder<T[number]> { return value => { const result = text(value); if (!values.includes(result)) throw new Error('Invalid choice'); return result as T[number]; }; }
/** fields是字段白名单；未知属性不会被复制。 */
function shape<T extends Record<string, Decoder<unknown>>>(fields: T): Decoder<{ [K in keyof T]: ReturnType<T[K]> }> {
  return value => { const data = objectValue(value); return Object.fromEntries(Object.entries(fields).map(([key, decode]) => [key, decode(data[key])])) as { [K in keyof T]: ReturnType<T[K]> }; };
}
/** value是契约未公开子字段的对象，只确认类型而不传递私有内容。 */
function opaque(value: unknown): Record<string, never> { objectValue(value); return {}; }
const texts = array(text), confidence = choice('high', 'medium', 'low'), intent = choice('diagnose', 'learn', 'retrieve', 'challenge', 'act');
const contextRefs = array(shape({ index: integer, kind: choice('fact', 'constraint', 'assumption') }));
const seat = shape({ card_ids: texts, claim: text, status: choice('represented', 'gap') });
const contentValue: Decoder<AnswerContent> = shape({
  schema_version: value => { if (value !== 3) throw new Error('Invalid version'); return 3 as const; },
  mode: choice('quick', 'standard', 'deep'), problem: opaque,
  problem_framing: shape({ confidence, diagnostic_summary: text, hidden_assumptions: texts, key_uncertainties: texts, reframed_question: text, surface_question: text }),
  books: array(shape({ author_display: nullable(text), book_id: text, title: text })),
  actions: array(shape({ basis_card_ids: texts, completion_criteria: text, step: text, stop_condition: text, validation_signal: text })),
  argument_relations: array(value => { const data = objectValue(value); return { ...shape({ explanation: text, from_card_ids: texts, to_claim: text, type: choice('support', 'attack', 'contradict', 'undercut', 'complement', 'depend_on') })(data), ...(data.condition === undefined ? {} : { condition: text(data.condition) }) }; }),
  call_ledger: shape({ admitted: texts, books_searched: texts, books_with_candidates: texts, candidates: array(opaque), queries: texts, rejected: array(opaque), retrieval_degraded: bool, retrieval_mode: text }),
  continuation_options: array(shape({ basis_card_ids: texts, description: text, intent, next_move: text, title: text })),
  knowledge_groups: array(shape({ card_ids: texts, open_questions: texts, purpose: text, synthesis: text, title: text })),
  learning_takeaways: array(shape({ basis_card_ids: texts, how_to_reuse: text, method: text })),
  next_chat_action: shape({ intent, prompt: text, reason: text }),
  roundtable: shape({ support: seat, opposition: seat, alternative: seat, evidence_audit: seat }),
  sources: array(shape({ author: nullable(text), book_id: text, book_title: text, card_ids: texts, chapter: text, evidence_id: text, excerpt: nullable(text), quote_available: bool })),
  system_syntheses: array(shape({ basis_card_ids: texts, confidence, content: text, title: text, type: choice('cross_book_synthesis', 'extension', 'hypothesis', 'analogy', 'new_option'), validation_needed: text })),
  verdict: shape({ basis_card_ids: texts, change_conditions: texts, conclusion: text, confidence, consensus: texts, decisive_user_context_refs: contextRefs, disagreements: texts, reasoning_summary: text, uncertainties: texts }),
  witness_cards: array(shape({ adopted_claim: text, assumptions: texts, author: nullable(text), author_id: text, book_id: text, book_title: text, card_id: text, chapters: texts, confidence, evidence_ids: texts, excluded_scope: texts, fit: choice('direct', 'partial', 'analogy', 'conflict'), independent_judgment: text, judgment_effect: text, mechanism: text, misuse_risks: texts, non_applicable_conditions: texts, principle: text, principle_gap: bool, quote: nullable(shape({ evidence_id: text, text })), roles: array(choice('support', 'challenge', 'boundary', 'alternative', 'evidence_auditor', 'action_translator')), situation_mapping: text, source_claim_type: choice('author_claim', 'quoted_other', 'system_inference', 'unclassified'), source_gap: bool, user_context_refs: contextRefs })),
});
/** value为响应，id/context核对当前选择的答案、任务、问题及知识版本。 */
export function decodeAnswer(value: unknown, id: string, context: AnswerContext): Answer {
  const data = objectValue(value), published = text(data.published_at);
  const result: Answer = { id: uuid(data.id), problem_id: uuid(data.problem_id), run_id: uuid(data.run_id), release_id: uuid(data.release_id), input_revision: integer(data.input_revision), published_at: published,
    content_hash: text(data.content_hash), validation_status: choice('structure_passed', 'semantic_reviewed')(data.validation_status), content: contentValue(data.content), rendered_markdown: text(data.rendered_markdown) };
  if (result.id !== uuid(id) || result.problem_id !== uuid(context.problemId) || result.run_id !== uuid(context.runId) || result.release_id !== uuid(context.releaseId) || result.input_revision !== context.inputRevision || !Number.isFinite(Date.parse(published))) throw new Error('Wrong answer');
  if (result.content.sources.some(source => !source.quote_available && source.excerpt !== null)) throw new Error('Invalid quote permission');
  for (const witness of result.content.witness_cards) {
    if (witness.quote && (!witness.evidence_ids.includes(witness.quote.evidence_id) || !result.content.sources.some(source => source.evidence_id === witness.quote!.evidence_id && source.quote_available && source.card_ids.includes(witness.card_id)))) throw new Error('Invalid witness quote');
  }
  return result;
}
/** id为真实job返回的答案ID，context约束归属，signal随页面选择或身份销毁。 */
export function readAnswer(id: string, context: AnswerContext, signal?: AbortSignal) {
  const expected = uuid(id);
  uuid(context.problemId); uuid(context.runId); uuid(context.releaseId);
  return requestJson(`/api/v1/answers/${expected}`, value => decodeAnswer(value, expected, context), { signal });
}
