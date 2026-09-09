/** 运营接口只接收账号状态与聚合；不返回聊天、反馈正文或邀请令牌。 */
import { objectValue, requestJson } from './client';
import type { ManagedUser } from './publishing';
import type { components } from './generated';

export type Quota = components['schemas']['AdminQuota'];
export type Operations = components['schemas']['AdminOperations'];
export type JobStatus = Operations['run_counts'][number]['status'];
export type FeedbackSummary = components['schemas']['AdminFeedbackSummary'];
export type FeedbackCategory = FeedbackSummary['category_counts'][number]['category'];
export type InvitationDelivery = components['schemas']['AdminInvitation'];
/** value为未知字符串；不隐式转换响应。 */
function text(value: unknown): string { if (typeof value !== 'string') throw new Error('Invalid text'); return value; }
/** value为公开UUID；固定路由参数也必须通过相同检查。 */
function uuid(value: unknown): string { const result = text(value); if (!/^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(result)) throw new Error('Invalid id'); return result.toLowerCase(); }
/** value是次数或修订号；拒绝负数、精度丢失和非数字。 */
function count(value: unknown): number { if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) throw new Error('Invalid count'); return value; }
/** value为UTC月首日期，避免将日统计误标为整月。 */
function period(value: unknown): string { const result = text(value); if (!/^\d{4}-(0[1-9]|1[0-2])-01$/.test(result)) throw new Error('Invalid period'); return result; }
/** value与allowed为响应字段和固定枚举。 */
function choice<T extends string>(value: unknown, allowed: readonly T[]): T { const result = text(value); if (!allowed.includes(result as T)) throw new Error('Invalid choice'); return result as T; }
/** value为已授权账号额度；保留服务端修订号供CAS提交。 */
function quota(value: unknown): Quota { const d = objectValue(value); const result = { owner_id: uuid(d.owner_id), period: period(d.period), limit_runs: count(d.limit_runs), reserved_runs: count(d.reserved_runs), settled_runs: count(d.settled_runs), revision: count(d.revision) }; if (result.limit_runs < result.reserved_runs + result.settled_runs) throw new Error('Invalid usage'); return result; }
/** owner为明确目标，signal绑定当前管理身份。 */
export function readQuota(owner: string, signal?: AbortSignal) { return requestJson(`/api/v1/admin/users/${uuid(owner)}/quota`, value => { const result = quota(value); if (result.owner_id !== owner.toLowerCase()) throw new Error('Wrong owner'); return result; }, { signal }); }
/** owner/limit/revision/expectedPeriod为已读取账号与月额度，key为一次明确写请求。 */
export function saveQuota(owner: string, limit: number, revision: number, expectedPeriod: string, key: string, signal?: AbortSignal) { return requestJson(`/api/v1/admin/users/${uuid(owner)}/quota`, value => { const result = quota(value); if (result.owner_id !== owner.toLowerCase() || result.period !== expectedPeriod) throw new Error('Wrong quota'); return result; }, { method: 'PUT', body: { limit_runs: limit, expected_revision: revision, expected_period: period(expectedPeriod) }, idempotencyKey: key, signal }); }
/** owner/status/expected/reason是人工确认状态变更，不接受管理身份或权限字段。 */
export function changeAccountStatus(owner: string, status: 'active' | 'disabled', expected: 'active' | 'disabled', reason: string, key: string, signal?: AbortSignal) { return requestJson(`/api/v1/admin/users/${uuid(owner)}/status`, value => { const d = objectValue(value); const result: ManagedUser = { id: uuid(d.id), email: text(d.email), display_name: text(d.display_name), status: choice(d.status, ['active', 'disabled'] as const) }; if (result.id !== owner.toLowerCase() || result.status !== status) throw new Error('Wrong account state'); return result; }, { method: 'POST', body: { status, expected_status: expected, reason }, idempotencyKey: key, signal }); }
/** email为人工输入邮箱；响应只能包含捕获投递凭条，不读取邀请秘密。 */
export function createInvitation(email: string, key: string, signal?: AbortSignal) { return requestJson('/api/v1/admin/invitations', (value): InvitationDelivery => { const d = objectValue(value), expires = text(d.expires_at); if (d.delivery !== 'local_capture' || !Number.isFinite(Date.parse(expires))) throw new Error('Invalid delivery'); return { delivery: 'local_capture', delivery_id: uuid(d.delivery_id), expires_at: expires }; }, { method: 'POST', body: { email }, idempotencyKey: key, signal }); }
/** signal绑定本次已授权统计读取；只接有限状态和一致总数。 */
export function readOperations(signal?: AbortSignal) { return requestJson('/api/v1/admin/operations', (value): Operations => { const d = objectValue(value); if (!Array.isArray(d.run_counts)) throw new Error('Invalid counts'); const rows = d.run_counts.map(value => { const row = objectValue(value); return { status: choice(row.status, ['queued', 'running', 'cancel_requested', 'succeeded', 'failed', 'cancelled'] as const), count: count(row.count) }; }); const total = count(d.total_runs); if (new Set(rows.map(row => row.status)).size !== rows.length || rows.reduce((sum, row) => sum + row.count, 0) !== total) throw new Error('Invalid total'); return { period: period(d.period), run_counts: rows, total_runs: total }; }, { signal }); }
/** signal绑定管理身份；只有聚合分类，不解析任何评论文本。 */
export function readFeedbackSummary(signal?: AbortSignal) { return requestJson('/api/v1/admin/feedback/summary', (value): FeedbackSummary => { const d = objectValue(value); if (!Array.isArray(d.category_counts)) throw new Error('Invalid categories'); const rows = d.category_counts.map(value => { const row = objectValue(value); return { category: choice(row.category, ['helpful', 'shallow', 'unclear_principle', 'wrong_source', 'other'] as const), count: count(row.count) }; }); const total = count(d.total_feedback); if (new Set(rows.map(row => row.category)).size !== rows.length || rows.reduce((sum, row) => sum + row.count, 0) !== total) throw new Error('Invalid total'); return { category_counts: rows, total_feedback: total }; }, { signal }); }
