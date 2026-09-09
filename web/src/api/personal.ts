/** 个人收藏与实践记录；公开类型由真实服务端契约生成，不在浏览器缓存私有内容。 */
import type { components } from './generated';
import { ApiFailure, objectValue, requestJson } from './client';

export type Bookmark = components['schemas']['Bookmark'];
export type ActionRecord = components['schemas']['ActionRecord'];
export type Feedback = components['schemas']['Feedback'];
export type ActionStatus = ActionRecord['status'];
/** value为未知JSON文本，不将对象强制转成字符串。 */
function text(value: unknown): string { if (typeof value !== 'string') throw new Error('Invalid text'); return value; }
/** value为公开UUID，阻止路径注入。 */
function uuid(value: unknown): string { const result = text(value); if (!/^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(result)) throw new ApiFailure('INVALID_RESPONSE'); return result.toLowerCase(); }
/** value为不可含路径分隔符的知识卡ID。 */
function cardId(value: unknown): string { const result = text(value); if (!result || result.length > 240 || /[\s/\\?#\u0000-\u001f]/u.test(result) || result === '.' || result === '..') throw new Error('Invalid card'); return result; }
/** value是服务端整数，不接受小数/布尔值或超安全范围。 */
function integer(value: unknown): number { if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) throw new Error('Invalid integer'); return value; }
/** value为时间戳，不把损坏日期作为有效保存时间。 */
function date(value: unknown): string { const result = text(value); if (!Number.isFinite(Date.parse(result))) throw new Error('Invalid date'); return result; }
/** value为枚举，choices是当前已实现取值。 */
function choice<const T extends readonly string[]>(value: unknown, choices: T): T[number] { if (typeof value !== 'string' || !choices.includes(value)) throw new Error('Invalid choice'); return value as T[number]; }
/** value为收藏投影；撤权占位不接受残留备注或隐含知识副本。 */
function bookmark(value: unknown): Bookmark {
  const d = objectValue(value);
  if (typeof d.available !== 'boolean' || (!d.available && d.note !== null)) throw new Error('Invalid access');
  return { id: uuid(d.id), release_id: uuid(d.release_id), core_card_id: cardId(d.core_card_id), available: d.available,
    note: d.note === null ? null : text(d.note), created_at: date(d.created_at), updated_at: date(d.updated_at) };
}
/** value为来自原答案的真实行动；只投影公开字段。 */
function action(value: unknown): ActionRecord {
  const d = objectValue(value);
  return { id: uuid(d.id), problem_id: uuid(d.problem_id), answer_id: uuid(d.answer_id), action_index: integer(d.action_index),
    status: choice(d.status, ['planned', 'doing', 'done', 'dropped']), observation: text(d.observation), revision: integer(d.revision),
    step: text(d.step), completion_criteria: text(d.completion_criteria), validation_signal: text(d.validation_signal), stop_condition: text(d.stop_condition),
    created_at: date(d.created_at), updated_at: date(d.updated_at) };
}
/** value为有界分页，decode决定每条记录白名单；不接受重复ID。 */
function page<T extends { id: string }>(value: unknown, decode: (value: unknown) => T): { items: T[]; next_cursor: string | null } {
  const d = objectValue(value);
  if (!Array.isArray(d.items) || d.items.length > 100) throw new Error('Invalid page');
  const items = d.items.map(decode), next_cursor = d.next_cursor === null ? null : text(d.next_cursor);
  if (new Set(items.map(item => item.id)).size !== items.length || (next_cursor !== null && (!next_cursor || next_cursor.length > 4096))) throw new Error('Invalid cursor');
  return { items, next_cursor };
}
/** query为本人分页；undefined值不得进入查询串（会被字面量化为"undefined"遭服务端拒绝）。 */
function pageSearch(query: { cursor?: string }): string {
  const params = new URLSearchParams();
  if (query.cursor !== undefined) params.set('cursor', query.cursor);
  // 历史URL形状恒带问号；测试桩与服务端都按此前缀匹配。
  return '?' + params.toString();
}
/** query为本人分页，signal在身份变化时取消。 */
export function readBookmarks(query: { cursor?: string } = {}, signal?: AbortSignal) { return requestJson('/api/v1/bookmarks' + pageSearch(query), value => page(value, bookmark), { signal, timeoutMs: 45000 }); }
/** release/card来自已授权卡片；PUT明确保存备注，不自动重发。 */
export function saveBookmark(release: string, card: string, note?: string, signal?: AbortSignal) {
  const r = uuid(release), c = cardId(card);
  return requestJson(`/api/v1/bookmarks/${r}/${encodeURIComponent(c)}`, value => { const result = bookmark(value); if (result.release_id !== r || result.core_card_id !== c || !result.available) throw new Error('Wrong bookmark'); return result; }, { method: 'PUT', body: note === undefined ? {} : { note }, signal, timeoutMs: 45000 });
}
/** release/card为本人收藏，失权后仍可主动删除；只接受204空结果。 */
export function removeBookmark(release: string, card: string, signal?: AbortSignal) { return requestJson(`/api/v1/bookmarks/${uuid(release)}/${encodeURIComponent(cardId(card))}`, value => { if (value !== undefined) throw new Error('Invalid deletion'); }, { method: 'DELETE', signal }); }
/** query为本人状态/问题过滤，与签名游标一同发送。 */
export function readActions(query: { cursor?: string; status?: ActionStatus; problem_id?: string } = {}, signal?: AbortSignal) {
  return requestJson('/api/v1/actions' + pageSearch(query), value => { const result = page(value, action); if (result.items.some(item => (query.status && item.status !== query.status) || (query.problem_id && item.problem_id !== query.problem_id))) throw new Error('Wrong filter'); return result; }, { signal, timeoutMs: 45000 });
}
/** answer/index引用实际答案行动，不允许客户端自行填写建议正文。 */
export function createAction(answer: string, index: number, signal?: AbortSignal) {
  const expected = uuid(answer); integer(index);
  return requestJson('/api/v1/actions', value => { const result = action(value); if (result.answer_id !== expected || result.action_index !== index) throw new Error('Wrong action'); return result; }, { method: 'POST', body: { answer_id: expected, action_index: index }, signal });
}
/** id为本人记录，data保留已显示修订，旧修订不能静默覆盖观察。 */
export function updateAction(id: string, data: components['schemas']['UpdateAction'], signal?: AbortSignal) {
  const expected = uuid(id);
  return requestJson('/api/v1/actions/' + expected, value => { const result = action(value); if (result.id !== expected) throw new Error('Wrong action'); return result; }, { method: 'PATCH', body: data, signal });
}
/** data为对当前答案的明确产品反馈，不冒充对原书的事实裁决。 */
export function sendFeedback(data: components['schemas']['CreateFeedback'], signal?: AbortSignal) {
  return requestJson('/api/v1/feedback', value => {
    const d = objectValue(value);
    const result: Feedback = { id: uuid(d.id), answer_id: uuid(d.answer_id), category: choice(d.category, ['helpful', 'shallow', 'unclear_principle', 'wrong_source', 'other']), comment: text(d.comment), created_at: date(d.created_at) };
    if (result.answer_id !== data.answer_id) throw new Error('Wrong feedback'); return result;
  }, { method: 'POST', body: data, signal });
}
