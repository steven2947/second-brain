/** 问题草稿公开API；类型来自生成契约，不把创建档案当成分析完成。 */
import type { components } from './generated';
import { ApiFailure, objectValue, requestJson } from './client';

export type Problem = components['schemas']['Problem'];
export type ProblemPage = components['schemas']['ProblemPage'];
export type CreateProblemInput = components['schemas']['CreateProblem'];
export type UpdateProblemInput = components['schemas']['UpdateProblem'];

/** value为公开UUID，不允许路径注入或内部标识。 */
function uuid(value: unknown): string {
  if (typeof value !== 'string' || !/^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(value)) throw new ApiFailure('INVALID_RESPONSE');
  return value.toLowerCase();
}
/** value为未知JSON字符串，不能强制转换用户表达。 */
function text(value: unknown): string { if (typeof value !== 'string') throw new Error('Invalid text'); return value; }
/** value为修订或轮数，只接受安全非负整数。 */
function integer(value: unknown): number { if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) throw new Error('Invalid count'); return value; }
/** value为公开布尔状态，不把字符串false当真。 */
function boolean(value: unknown): boolean { if (typeof value !== 'boolean') throw new Error('Invalid boolean'); return value; }
/** value为服务端枚举，choices为本操作实际允许值。 */
function choice<const T extends readonly string[]>(value: unknown, choices: T): T[number] {
  if (typeof value !== 'string' || !choices.includes(value)) throw new Error('Invalid choice');
  return value as T[number];
}
/** value为时间戳，避免损坏的日期在页面伪装为有效时间。 */
function date(value: unknown): string { const result = text(value); if (!Number.isFinite(Date.parse(result))) throw new Error('Invalid date'); return result; }
/** value为问题详情；只返回公开字段，澄清不能出现第六轮。 */
export function decodeProblem(value: unknown): Problem {
  const data = objectValue(value), clarification = objectValue(data.clarification);
  const rounds = integer(clarification.rounds), limit = integer(clarification.limit);
  if (limit < 1 || limit > 5 || rounds > limit) throw new Error('Invalid intake');
  return { id: uuid(data.id), title: text(data.title), original_question: text(data.original_question),
    goal: choice(data.goal, ['explain', 'analyze', 'compare', 'act', 'review']), release_id: uuid(data.release_id),
    revision: integer(data.revision), status: choice(data.status, ['active', 'archived']),
    clarification: { rounds, limit, pending_question: clarification.pending_question === null ? null : text(clarification.pending_question), closed: boolean(clarification.closed) },
    current_answer_id: data.current_answer_id === null ? null : uuid(data.current_answer_id),
    library_available: boolean(data.library_available), created_at: date(data.created_at), updated_at: date(data.updated_at) };
}
/** value为本人有界档案列表，不缓存到浏览器存储。 */
function decodePage(value: unknown): ProblemPage {
  const data = objectValue(value);
  if (!Array.isArray(data.items) || data.items.length > 100) throw new Error('Invalid page');
  const items = data.items.map(decodeProblem);
  if (new Set(items.map(item => item.id)).size !== items.length) throw new Error('Duplicate problem');
  const next_cursor = data.next_cursor === null ? null : text(data.next_cursor);
  if (next_cursor !== null && (!next_cursor || next_cursor.length > 4096)) throw new Error('Invalid cursor');
  return { items, next_cursor };
}
/** query为本人列表过滤，signal取消卸载页面的读取。 */
export function readProblems(query: { q?: string; status?: 'active' | 'archived'; cursor?: string } = {}, signal?: AbortSignal) {
  const params = new URLSearchParams(query);
  return requestJson('/api/v1/problems?' + params, decodePage, { signal });
}
/** id为目标档案；只接受对应对象，错误ID不作为页面内容。 */
export function readProblem(id: string, signal?: AbortSignal) {
  const expected = uuid(id);
  return requestJson('/api/v1/problems/' + expected, value => { const result = decodeProblem(value); if (result.id !== expected) throw new Error('Wrong problem'); return result; }, { signal });
}
/** data为原问题和固定版本；key由一次用户提交生成，重试须保留同键，不自动重发。 */
export function createProblem(data: CreateProblemInput, key: string, signal?: AbortSignal) {
  return requestJson('/api/v1/problems', decodeProblem, { method: 'POST', body: data, idempotencyKey: key, signal });
}
/** id为本人档案，data包含已显示修订；服务器负责并发冲突，客户端不覆盖。 */
export function updateProblem(id: string, data: UpdateProblemInput, signal?: AbortSignal) {
  const expected = uuid(id);
  return requestJson('/api/v1/problems/' + expected, value => { const result = decodeProblem(value); if (result.id !== expected) throw new Error('Wrong problem'); return result; }, { method: 'PATCH', body: data, signal });
}
