/** 消息与任务API；公开DTO来自生成契约，响应逐字段校验且写操作不自动重试。 */
import type { components } from './generated';
import { ApiFailure, objectValue, requestJson } from './client';

export type MessagePage = components['schemas']['MessagePage'];
export type Message = MessagePage['items'][number];
export type AcceptedRun = components['schemas']['AcceptedRun'];
export type SendMessage = components['schemas']['SendMessage'];
export type Analyze = components['schemas']['Analyze'];
export type Run = components['schemas']['Run'];
export type Job = components['schemas']['Job'];
const statuses = ['queued', 'running', 'cancel_requested', 'succeeded', 'failed', 'cancelled'] as const;
const stages = ['accepted', 'understanding', 'retrieving', 'evaluating', 'validating', 'composing'] as const;
const errors = ['MODEL_UNAVAILABLE', 'MODEL_OUTPUT_INVALID', 'RUN_TIMEOUT', 'RUN_CANCELLED', 'RUN_STALE', 'ACCESS_REVOKED', 'RUN_FAILED', 'ANALYSIS_UNAVAILABLE'] as const;
/** value为公开UUID，只接受完整标识，不允许路径注入。 */
function uuid(value: unknown): string {
  if (typeof value !== 'string' || !/^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(value)) throw new ApiFailure('INVALID_RESPONSE');
  return value.toLowerCase();
}
/** value为未知字符串，不通过强制转换接受错误字段。 */
function text(value: unknown): string { if (typeof value !== 'string') throw new Error('Invalid text'); return value; }
/** value为修订或序号，min限制最小值。 */
function integer(value: unknown, min = 0): number { if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < min) throw new Error('Invalid integer'); return value; }
/** value为布尔字段，拒绝字符串或数字替代。 */
function boolean(value: unknown): boolean { if (typeof value !== 'boolean') throw new Error('Invalid boolean'); return value; }
/** value为枚举原值，allowed列出本接口所有已知值。 */
function choice<const T extends readonly string[]>(value: unknown, allowed: T): T[number] {
  if (typeof value !== 'string' || !allowed.includes(value)) throw new Error('Invalid choice');
  return value as T[number];
}
/** value为日期原值；只接受可解析日期。 */
function date(value: unknown): string { const result = text(value); if (!Number.isFinite(Date.parse(result))) throw new Error('Invalid date'); return result; }
/** value可为null，decode用于非空字段的具体校验。 */
function nullable<T>(value: unknown, decode: (value: unknown) => T): T | null { return value === null ? null : decode(value); }
/** value为真实202入队凭据，revision为本次提交已读修订。 */
function accepted(value: unknown, revision: number): AcceptedRun {
  const data = objectValue(value), result = { run_id: uuid(data.run_id), job_id: uuid(data.job_id), revision: integer(data.revision) };
  if (result.revision !== revision + 1) throw new Error('Wrong revision');
  return result;
}
/** value为消息分页，problemId限定消息归属；未知额外字段不会传到UI。 */
function messagePage(value: unknown, problemId: string): MessagePage {
  const data = objectValue(value);
  if (!Array.isArray(data.items) || data.items.length > 100) throw new Error('Invalid page');
  const items: Message[] = data.items.map(value => {
    const row = objectValue(value);
    const message: Message = { id: uuid(row.id), problem_id: uuid(row.problem_id), sequence: integer(row.sequence, 1),
      role: choice(row.role, ['user', 'assistant']), kind: choice(row.kind, ['user_text', 'clarification', 'answer', 'notice']),
      content: text(row.content), client_message_id: nullable(row.client_message_id, uuid), run_id: nullable(row.run_id, uuid),
      published_at: nullable(row.published_at, date), created_at: date(row.created_at) };
    if (message.problem_id !== problemId || (message.role === 'assistant' && message.published_at === null)) throw new Error('Wrong message');
    return message;
  });
  if (new Set(items.map(item => item.id)).size !== items.length || items.some((item, index) => index > 0 && item.sequence <= items[index - 1].sequence)) throw new Error('Invalid ordering');
  const next_cursor = nullable(data.next_cursor, text), library_available = boolean(data.library_available);
  if (next_cursor !== null && (!next_cursor || next_cursor.length > 4096)) throw new Error('Invalid cursor');
  if (!library_available && items.some(item => item.role !== 'user')) throw new Error('Unavailable knowledge');
  return { items, next_cursor, revision: integer(data.revision), library_available };
}
/** data为任务公开字段，两种任务视图共用固定阶段与错误码白名单。 */
function taskFields(data: Record<string, unknown>) {
  return { id: uuid(data.id), problem_id: uuid(data.problem_id), status: choice(data.status, statuses), stage: choice(data.stage, stages),
    error_code: nullable(data.error_code, value => choice(value, errors)), started_at: nullable(data.started_at, date), finished_at: nullable(data.finished_at, date) };
}
/** value为job视图，id/context约束本人当前问题与run关联。 */
function jobValue(value: unknown, id: string, context?: { problemId: string; runId: string }): Job {
  const data = objectValue(value), result = { ...taskFields(data), run_id: uuid(data.run_id), result_ref: nullable(data.result_ref, uuid) };
  if (result.id !== id || context && (result.problem_id !== uuid(context.problemId) || result.run_id !== uuid(context.runId))) throw new Error('Wrong job');
  return result;
}
/** id为本人问题，cursor为服务端签名游标，signal用于中止页面读取。 */
export function listMessages(id: string, cursor?: string, signal?: AbortSignal) {
  const expected = uuid(id), query = cursor ? '?' + new URLSearchParams({ cursor }) : '';
  return requestJson(`/api/v1/problems/${expected}/messages${query}`, value => messagePage(value, expected), { signal });
}
/** id为本人问题，data保留消息原文与意图，key重试须复用，signal取消当前请求。 */
export function sendMessage(id: string, data: SendMessage, key: string, signal?: AbortSignal) {
  return requestJson(`/api/v1/problems/${uuid(id)}/messages`, value => accepted(value, data.expected_revision), { method: 'POST', body: data, idempotencyKey: key, signal });
}
/** id为本人问题，data仅含已读修订，key绑定一次明确分析，signal取消请求。 */
export function startAnalysis(id: string, data: Analyze, key: string, signal?: AbortSignal) {
  return requestJson(`/api/v1/problems/${uuid(id)}/analyze`, value => accepted(value, data.expected_revision), { method: 'POST', body: data, idempotencyKey: key, signal });
}
/** id为公开运行ID，signal取消读取，problemId可核对当前页面归属。 */
export function readRun(id: string, signal?: AbortSignal, problemId?: string) {
  const expected = uuid(id);
  return requestJson(`/api/v1/runs/${expected}`, value => {
    const data = objectValue(value);
    const result: Run = { ...taskFields(data), job_id: uuid(data.job_id), input_revision: integer(data.input_revision), stale: boolean(data.stale),
      outcome: nullable(data.outcome, value => choice(value, ['question', 'answer', 'coverage_gap', 'unavailable'])) };
    if (result.id !== expected || problemId && result.problem_id !== uuid(problemId)) throw new Error('Wrong run');
    return result;
  }, { signal });
}
/** id为job ID，signal取消读取，context约束当前问题和运行。 */
export function readJob(id: string, signal?: AbortSignal, context?: { problemId: string; runId: string }) {
  const expected = uuid(id);
  return requestJson(`/api/v1/jobs/${expected}`, value => jobValue(value, expected, context), { signal });
}
/** id为job ID，signal中止当前请求，context验证响应归属；只发送一次取消。 */
export function cancelJob(id: string, signal?: AbortSignal, context?: { problemId: string; runId: string }) {
  const expected = uuid(id);
  return requestJson(`/api/v1/jobs/${expected}/cancel`, value => jobValue(value, expected, context), { method: 'POST', signal });
}
