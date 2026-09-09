/** 隐私API只处理本人元数据和明确导出；不把密码、文件链接放入客户端持久存储。 */
import { objectValue, requestJson } from './client';
import { decodeProblem } from './problems';
import type { components } from './generated';
export type ExportRecord = components['schemas']['PersonalExport'];
export type ExportScope = ExportRecord['scope'];
export type TrashRecord = components['schemas']['TrashPage']['items'][number];
export type DeletionReceipt = components['schemas']['AccountDeletion'];
type Page<T> = { items: T[]; next_cursor: string | null };
/** value为文本，拒绝隐式转换。 */
function text(value: unknown): string { if (typeof value !== 'string') throw new Error('Invalid text'); return value; }
/** value为UUID，响应和路径共用校验，避免任意路径输入。 */
function uuid(value: unknown): string { const result = text(value); if (!/^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(result)) throw new Error('Invalid id'); return result.toLowerCase(); }
/** value为时间戳，只接受有效时间。 */
function date(value: unknown): string { const result = text(value); if (!Number.isFinite(Date.parse(result))) throw new Error('Invalid date'); return result; }
/** value为修订号，不允许精度丢失。 */
function count(value: unknown): number { if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) throw new Error('Invalid count'); return value; }
/** value与allowed为未知状态和固定允许值，不把新状态猜成完成。 */
function choice<T extends string>(value: unknown, allowed: readonly T[]): T { const result = text(value); if (!allowed.includes(result as T)) throw new Error('Invalid choice'); return result as T; }
/** value为当前导出任务公开状态，ready必须有下载时限。 */
function exportRecord(value: unknown): ExportRecord { const d = objectValue(value); const result = { id: uuid(d.id), scope: choice(d.scope, ['problems', 'learning', 'all_personal'] as const), status: choice(d.status, ['queued', 'running', 'ready', 'failed', 'expired'] as const), created_at: date(d.created_at), expires_at: d.expires_at === null ? null : date(d.expires_at), error_code: d.error_code === null ? null : text(d.error_code) }; if (result.status === 'ready' && !result.expires_at) throw new Error('Missing expiry'); return result; }
/** value为分页响应，decode只挑选当前资源白名单字段。 */
function page<T extends { id: string }>(value: unknown, decode: (value: unknown) => T): Page<T> { const d = objectValue(value); if (!Array.isArray(d.items) || d.items.length > 100) throw new Error('Invalid list'); const items = d.items.map(decode), next_cursor = d.next_cursor === null ? null : text(d.next_cursor); if (new Set(items.map(item => item.id)).size !== items.length || (next_cursor !== null && (!next_cursor || next_cursor.length > 4096))) throw new Error('Invalid page'); return { items, next_cursor }; }
/** cursor来自实际分页响应，不拼接私有信息到路径。 */
function query(cursor?: string | null): string { return '?' + new URLSearchParams(cursor ? { cursor } : {}); }
/** scope/password是本次明确输入，key只代表选择范围，不包含密码派生值。 */
export function requestExport(scope: ExportScope, password: string, key: string, signal?: AbortSignal) { return requestJson('/api/v1/me/exports', exportRecord, { method: 'POST', body: { scope, password }, idempotencyKey: key, signal }); }
/** cursor/signal限定当前身份和页面。 */
export function readExports(cursor?: string | null, signal?: AbortSignal) { return requestJson('/api/v1/me/exports' + query(cursor), value => page(value, exportRecord), { signal }); }
/** id是任务UUID；只接受同任务状态，不采用另一个文件的完成结果。 */
export function readExport(id: string, signal?: AbortSignal) { return requestJson(`/api/v1/me/exports/${uuid(id)}`, value => { const result = exportRecord(value); if (result.id !== id.toLowerCase()) throw new Error('Wrong export'); return result; }, { signal }); }
/** id/scope绑定本次明确下载；只接JSON附件，不跟随公开链接或渲染原始HTML。 */
export function downloadExport(id: string, scope: ExportScope, signal?: AbortSignal) { return requestJson(`/api/v1/me/exports/${uuid(id)}/download`, value => { const d = objectValue(value); if (d.schema_version !== 1 || uuid(d.export_id) !== id.toLowerCase() || d.scope !== scope) throw new Error('Wrong download'); date(d.generated_at); return new Blob([JSON.stringify(d, null, 2)], { type: 'application/json' }); }, { signal, timeoutMs: 60000 }); }
/** cursor/signal为本人回收站，不读取已删除问题的答案或知识卡正文。 */
export function readTrash(cursor?: string | null, signal?: AbortSignal) { return requestJson('/api/v1/me/trash' + query(cursor), value => page(value, (item): TrashRecord => { const d = objectValue(item); return { id: uuid(d.id), title: text(d.title), status: choice(d.status, ['deleted'] as const), revision: count(d.revision), deleted_at: date(d.deleted_at), purge_after: date(d.purge_after) }; }), { signal }); }
/** id/revision为当前问题快照，DELETE仅送回收站，不立即物理清理。 */
export function trashProblem(id: string, revision: number, signal?: AbortSignal) { return requestJson(`/api/v1/problems/${uuid(id)}`, value => { if (value !== undefined) throw new Error('Invalid deletion'); }, { method: 'DELETE', body: { expected_revision: revision }, signal }); }
/** id/revision为本人回收站条目，恢复归档不代表重新获得知识授权。 */
export function restoreProblem(id: string, revision: number, signal?: AbortSignal) { return requestJson(`/api/v1/problems/${uuid(id)}/restore`, value => { const result = decodeProblem(value); if (result.id !== id.toLowerCase() || result.status !== 'archived') throw new Error('Wrong restoration'); return result; }, { method: 'POST', body: { expected_revision: revision }, signal }); }
/** password/confirmation为本次明确注销，只有202确认才展示受理，不推定已清理。 */
export function requestDeletion(password: string, confirmation: string, signal?: AbortSignal) { return requestJson('/api/v1/me/deletion', (value): DeletionReceipt => { const d = objectValue(value); return { id: uuid(d.id), status: choice(d.status, ['pending'] as const), requested_at: date(d.requested_at), purge_after: date(d.purge_after) }; }, { method: 'POST', body: { password, confirmation }, signal }); }
