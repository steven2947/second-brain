/** 独立学习公开接口；只保留本次页面内容，写入由用户明确发起且不自动重试。 */
import { ApiFailure, objectValue, requestJson } from './client';
import type { CardSummary } from './knowledge';
import type { components } from './generated';

export type LearningSession = components['schemas']['LearningSession'];
export type LearningTurn = components['schemas']['LearningTurn'];
export type LearningJob = components['schemas']['LearningJob'];
export type LearningDetail = components['schemas']['LearningDetail'];
export type CreateLearning = components['schemas']['CreateLearning'];
export type SendLearningMessage = components['schemas']['SendLearningMessage'];

/** value为未知文本，不进行隐式转换。 */
function text(value: unknown): string { if (typeof value !== 'string') throw new Error('Invalid text'); return value; }
/** value为公开UUID，非法路径在请求前拒绝。 */
function uuid(value: unknown): string { const result = text(value); if (!/^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(result)) throw new ApiFailure('INVALID_REQUEST'); return result.toLowerCase(); }
/** value为实际整数，拒绝布尔值与非安全整数。 */
function integer(value: unknown): number { if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) throw new Error('Invalid integer'); return value; }
/** value为公开枚举，allowed列出本接口支持的取值。 */
function choice<const T extends readonly string[]>(value: unknown, allowed: T): T[number] { if (typeof value !== 'string' || !allowed.includes(value)) throw new Error('Invalid choice'); return value as T[number]; }
/** value可空；decode校验非空原值。 */
function nullable<T>(value: unknown, decode: (value: unknown) => T): T | null { return value === null ? null : decode(value); }
/** value为未知列表；decode物化白名单而不是直接转型。 */
function rows<T>(value: unknown, decode: (item: unknown) => T): T[] { if (!Array.isArray(value)) throw new Error('Invalid list'); return value.map(decode); }
/** value为服务器游标，不能成为任意URL。 */
function cursor(value: unknown) { return nullable(value, item => { const result = text(item); if (!result || result.length > 4096) throw new Error('Invalid cursor'); return result; }); }
/** value为知识ID列表；不接受空白、重复或路径符。 */
function cardIds(value: unknown) { const ids = rows(value, item => { const id = text(item); if (!id || /[\s/\\?#\u0000-\u001f]/u.test(id) || id === '.' || id === '..') throw new Error('Invalid card'); return id; }); if (new Set(ids).size !== ids.length) throw new Error('Duplicate cards'); return ids; }
/** value为服务端会话，仅返回公开字段。 */
function session(value: unknown): LearningSession {
  const d = objectValue(value);
  return { id: uuid(d.id), release_id: uuid(d.release_id), problem_id: nullable(d.problem_id, uuid), title: text(d.title), goal: text(d.goal), basis_card_ids: cardIds(d.basis_card_ids), revision: integer(d.revision), status: choice(d.status, ['active', 'archived']), created_at: text(d.created_at), updated_at: text(d.updated_at) };
}
/** value为回合，id绑定当前学习，所有渲染内容由React转义。 */
function turn(value: unknown, id: string): LearningTurn {
  const d = objectValue(value), c = objectValue(d.content);
  const result: LearningTurn = { id: uuid(d.id), learning_session_id: uuid(d.learning_session_id), sequence: integer(d.sequence), kind: choice(d.kind, ['user_request', 'explanation', 'exercise', 'user_response', 'feedback']), content: { text: text(c.text), sections: rows(c.sections, value => { const s = objectValue(value); return { title: text(s.title), body: text(s.body), basis_card_ids: cardIds(s.basis_card_ids) }; }) }, run_id: nullable(d.run_id, uuid), responds_to_turn_id: nullable(d.responds_to_turn_id, uuid), created_at: text(d.created_at) };
  if (result.learning_session_id !== id || result.sequence < 1 || result.kind === 'feedback' && !result.responds_to_turn_id) throw new Error('Wrong turn'); return result;
}
/** value为真实学习任务，id与jobId限制父域和所查任务。 */
function job(value: unknown, id: string, jobId?: string): LearningJob {
  const d = objectValue(value);
  const result: LearningJob = { id: uuid(d.id), learning_session_id: uuid(d.learning_session_id), run_id: uuid(d.run_id), status: choice(d.status, ['queued', 'running', 'cancel_requested', 'succeeded', 'failed', 'cancelled']), stage: choice(d.stage, ['accepted', 'understanding', 'retrieving', 'evaluating', 'validating', 'composing']), error_code: nullable(d.error_code, text), started_at: nullable(d.started_at, text), finished_at: nullable(d.finished_at, text) };
  if (result.learning_session_id !== id || jobId && result.id !== jobId) throw new Error('Wrong job'); return result;
}
/** value为公开卡片摘要；只能来自当前session选择的同release卡片。 */
function card(value: unknown, s: LearningSession): CardSummary {
  const d = objectValue(value), b = objectValue(d.book);
  const result: CardSummary = { release_id: uuid(d.release_id), card_id: text(d.card_id), title: text(d.title), statement: text(d.statement), type: text(d.type), book: { id: text(b.id), title: text(b.title), author_display: nullable(b.author_display, text), metadata_status: choice(b.metadata_status, ['verified', 'partial']) } };
  if (result.release_id !== s.release_id || !s.basis_card_ids.includes(result.card_id)) throw new Error('Wrong source'); return result;
}
/** status/cursor为实际分页；signal跟随私有页面销毁。 */
export function listLearning(query: { status?: 'active' | 'archived'; cursor?: string } = {}, signal?: AbortSignal) {
  const params = new URLSearchParams();
  if (query.status !== undefined) params.set('status', query.status);
  if (query.cursor !== undefined) params.set('cursor', query.cursor);
  // 历史URL形状恒带问号；测试桩与服务端都按此前缀匹配。
  return requestJson('/api/v1/learning?' + params.toString(), value => { const d = objectValue(value), items = rows(d.items, session); if (items.length > 100 || new Set(items.map(item => item.id)).size !== items.length || query.status && items.some(item => item.status !== query.status)) throw new Error('Invalid page'); return { items, next_cursor: cursor(d.next_cursor) }; }, { signal, timeoutMs: 45000 });
}
/** data为所选卡片和学习目标；key用于结果未知时同体重试。 */
export function createLearning(data: CreateLearning, key: string, signal?: AbortSignal) {
  return requestJson('/api/v1/learning', value => { const s = session(value); if (s.release_id !== uuid(data.release_id) || s.goal !== data.goal || s.basis_card_ids.length !== data.basis_card_ids.length || s.basis_card_ids.some(id => !data.basis_card_ids.includes(id))) throw new Error('Wrong session'); return s; }, { method: 'POST', body: data, idempotencyKey: key, signal, timeoutMs: 45000 });
}
/** id为当前会话，pageCursor来自服务端签名，返回前复核来源和回合归属。 */
export function readLearning(id: string, pageCursor?: string, signal?: AbortSignal) {
  const expected = uuid(id);
  return requestJson(`/api/v1/learning/${expected}` + (pageCursor ? '?' + new URLSearchParams({ cursor: pageCursor }) : ''), value => {
    const d = objectValue(value), s = session(d.session), items = rows(d.items, value => turn(value, expected));
    if (s.id !== expected || d.library_available !== true || items.length > 100 || new Set(items.map(item => item.id)).size !== items.length || items.some((item, index) => index > 0 && item.sequence <= items[index - 1].sequence) || items.some(item => item.content.sections.some(section => section.basis_card_ids.some(id => !s.basis_card_ids.includes(id))))) throw new Error('Invalid learning page');
    return { session: s, items, next_cursor: cursor(d.next_cursor), library_available: true, active_job: nullable(d.active_job, value => job(value, expected)), basis_cards: rows(d.basis_cards, value => card(value, s)) } satisfies LearningDetail;
  }, { signal, timeoutMs: 45000 });
}
/** id为会话，data保留用户原话，key和客户端消息ID用于同体重试。 */
export function sendLearningMessage(id: string, data: SendLearningMessage, key: string, signal?: AbortSignal) {
  return requestJson(`/api/v1/learning/${uuid(id)}/messages`, value => { const d = objectValue(value), revision = integer(d.revision); if (revision !== data.expected_revision + 1) throw new Error('Wrong revision'); return { run_id: uuid(d.run_id), job_id: uuid(d.job_id), revision }; }, { method: 'POST', body: data, idempotencyKey: key, signal, timeoutMs: 45000 });
}
/** id/jobId是当前学习任务，读取只接收同父域响应。 */
export function readLearningJob(id: string, jobId: string, signal?: AbortSignal) { const s = uuid(id), j = uuid(jobId); return requestJson(`/api/v1/learning/${s}/jobs/${j}`, value => job(value, s, j), { signal }); }
/** id/jobId绑定已显示任务，取消不是前端自行声明任务终止。 */
export function cancelLearningJob(id: string, jobId: string, signal?: AbortSignal) { const s = uuid(id), j = uuid(jobId); return requestJson(`/api/v1/learning/${s}/jobs/${j}/cancel`, value => job(value, s, j), { method: 'POST', signal }); }
/** id/revision为本人当前会话；归档不清理既有学习记录。 */
export function archiveLearning(id: string, revision: number, signal?: AbortSignal) { const s = uuid(id); return requestJson(`/api/v1/learning/${s}/archive`, value => { const result = session(value); if (result.id !== s || result.status !== 'archived') throw new Error('Wrong archive'); return result; }, { method: 'POST', body: { expected_revision: revision }, signal }); }
