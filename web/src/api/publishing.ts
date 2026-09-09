/** 管理知识接口只收公开DTO，来源路径和完整权利证明不进入浏览器。 */
import { objectValue, requestJson } from './client';
import type { components } from './generated';

export type ReleaseStatus = 'staged' | 'validated' | 'published' | 'revoked';
export type RightsStatus = 'unreviewed' | 'approved' | 'rejected' | 'expired';
export type Source = components['schemas']['AdminSources']['items'][number];
export type ImportJob = components['schemas']['AdminImport'];
export type ManagedRelease = components['schemas']['AdminRelease'];
export type RightsInput = components['schemas']['RightsInput']['records'][number];
export type RightsSummary = { id: string; status: RightsStatus; basis_type: string; scope_book_ids: string[]; allowed_uses: string[]; valid_until: string | null };
export type ReleaseDetail = ManagedRelease & { books: { id: string; title: string; author_display: string | null }[]; rights_records: RightsSummary[] };
export type ManagedUser = components['schemas']['AdminUsers']['items'][number];
export type Page<T> = { items: T[]; next_cursor: string | null };
/** value为公开文本，禁止隐式转换。 */
function text(value: unknown): string { if (typeof value !== 'string') throw new Error('Invalid text'); return value; }
/** value为公开UUID；既用于响应核验，也用于固定路由参数。 */
function uuid(value: unknown): string { const result = text(value); if (!/^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(result)) throw new Error('Invalid id'); return result.toLowerCase(); }
/** value为公开计数，必须是非负安全整数。 */
function count(value: unknown): number { if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) throw new Error('Invalid count'); return value; }
/** value是可空日期，不把任意文本当成有效时效。 */
function date(value: unknown): string | null { if (value === null) return null; const result = text(value); if (!Number.isFinite(Date.parse(result))) throw new Error('Invalid date'); return result; }
/** value为状态文本；allowed由本接口固定，未知状态不伪装成功。 */
function choice<T extends string>(value: unknown, allowed: readonly T[]): T { const result = text(value); if (!allowed.includes(result as T)) throw new Error('Invalid status'); return result as T; }
/** value为列表，decode逐条挑选公开字段。 */
function items<T>(value: unknown, decode: (item: unknown) => T): T[] { if (!Array.isArray(value)) throw new Error('Invalid list'); return value.map(decode); }
/** value为分页响应，decode不复制未声明字段。 */
function page<T>(value: unknown, decode: (item: unknown) => T): Page<T> { const d = objectValue(value); return { items: items(d.items, decode), next_cursor: d.next_cursor === null ? null : text(d.next_cursor) }; }
/** value为源登记公开信息，没有任意磁盘路径。 */
function source(value: unknown): Source { const d = objectValue(value); return { staging_key: text(d.staging_key), title: text(d.title), content_version: text(d.content_version), book_count: count(d.book_count), card_count: count(d.card_count) }; }
/** value为真实持久导入任务，不接受伪造的成功缺结果状态。 */
function job(value: unknown): ImportJob { const d = objectValue(value); const result = { id: uuid(d.id), status: choice(d.status, ['queued', 'running', 'succeeded', 'failed'] as const), stage: text(d.stage), release_id: d.release_id === null ? null : uuid(d.release_id), error_code: d.error_code === null ? null : text(d.error_code) }; if (result.status === 'succeeded' && !result.release_id) throw new Error('Missing release'); return result; }
/** value为管理版本摘要，仅显示计数、状态和内容版本。 */
function release(value: unknown): ManagedRelease { const d = objectValue(value); return { id: uuid(d.id), title: text(d.title), description: text(d.description), content_version: text(d.content_version), status: choice(d.status, ['staged', 'validated', 'published', 'revoked'] as const), rights_status: choice(d.rights_status, ['unreviewed', 'approved', 'rejected', 'expired'] as const), book_count: count(d.book_count), card_count: count(d.card_count) }; }
/** value为受保护管理详情；书名作者与权利摘要分别展示，不读取证明正文。 */
function detail(value: unknown): ReleaseDetail {
  const d = objectValue(value);
  return { ...release(value), books: items(d.books, item => { const b = objectValue(item); return { id: text(b.id), title: text(b.title), author_display: b.author_display === null ? null : text(b.author_display) }; }), rights_records: items(d.rights_records, item => { const r = objectValue(item); return { id: uuid(r.id), status: choice(r.status, ['unreviewed', 'approved', 'rejected', 'expired'] as const), basis_type: text(r.basis_type), scope_book_ids: items(r.scope_book_ids, text), allowed_uses: items(r.allowed_uses, text), valid_until: date(r.valid_until) }; }) };
}
/** cursor来自已验证响应，不拼入任意路径。 */
function cursorQuery(cursor?: string | null): string { return cursor ? `?${new URLSearchParams({ cursor })}` : ''; }
/** signal绑定当前管理身份。 */
export function listSources(signal?: AbortSignal) { return requestJson('/api/v1/admin/sources', value => items(objectValue(value).items, source), { signal }); }
/** cursor/signal用于本管理员导入记录的恢复与分页。 */
export function listImports(cursor?: string | null, signal?: AbortSignal) { return requestJson(`/api/v1/admin/imports${cursorQuery(cursor)}`, value => page(value, job), { signal }); }
/** stagingKey为已登记选择，key仅标记一次明确提交。 */
export function importSource(stagingKey: string, key: string, signal?: AbortSignal) { return requestJson('/api/v1/admin/releases/import', value => ({ job_id: uuid(objectValue(value).job_id) }), { method: 'POST', body: { staging_key: stagingKey }, idempotencyKey: key, signal }); }
/** cursor/signal用于获准管理版本摘要分页。 */
export function listManagedReleases(cursor?: string | null, signal?: AbortSignal) { return requestJson(`/api/v1/admin/releases${cursorQuery(cursor)}`, value => page(value, release), { signal }); }
/** id是版本UUID；返回详情必须属于请求版本。 */
export function readManagedRelease(id: string, signal?: AbortSignal) { return requestJson(`/api/v1/admin/releases/${uuid(id)}`, value => { const result = detail(value); if (result.id !== id.toLowerCase()) throw new Error('Wrong release'); return result; }, { signal }); }
/** id/records是人工提交的完整审核记录集，不自动勾选同意或附加用途。 */
export function saveRights(id: string, records: RightsInput[], key: string, signal?: AbortSignal) { return requestJson(`/api/v1/admin/releases/${uuid(id)}/rights`, release, { method: 'PUT', body: { records }, idempotencyKey: key, signal }); }
/** id/status为当前已读状态，只有明确点击才能发布。 */
export function publishRelease(id: string, status: ReleaseStatus, key: string, signal?: AbortSignal) { return requestJson(`/api/v1/admin/releases/${uuid(id)}/publish`, release, { method: 'POST', body: { expected_status: status }, idempotencyKey: key, signal, timeoutMs: 60000 }); }
/** id/status/reason为管理员的明确撤销输入，撤销不删除原书。 */
export function revokeRelease(id: string, status: ReleaseStatus, reason: string, key: string, signal?: AbortSignal) { return requestJson(`/api/v1/admin/releases/${uuid(id)}/revoke`, release, { method: 'POST', body: { expected_status: status, reason }, idempotencyKey: key, signal }); }
/** cursor/signal只读取管理账号摘要，不读取用户问题。 */
export function listManagedUsers(cursor?: string | null, signal?: AbortSignal) { return requestJson(`/api/v1/admin/users${cursorQuery(cursor)}`, value => page(value, item => { const u = objectValue(item); return { id: uuid(u.id), email: text(u.email), display_name: text(u.display_name), status: choice(u.status, ['active', 'disabled', 'deletion_pending'] as const) }; }), { signal }); }
/** owner/releaseId为显式选择的普通账号及版本，expiresAt为绝对时间或无期限。 */
export function grantRelease(owner: string, releaseId: string, expiresAt: string | null, key: string, signal?: AbortSignal) { return requestJson(`/api/v1/admin/users/${uuid(owner)}/grants/${uuid(releaseId)}`, value => { const d = objectValue(value); if (uuid(d.owner_id) !== owner.toLowerCase() || uuid(d.release_id) !== releaseId.toLowerCase() || d.status !== 'active') throw new Error('Wrong grant'); return { id: uuid(d.id), owner_id: uuid(d.owner_id), release_id: uuid(d.release_id), status: 'active' as const, expires_at: date(d.expires_at) }; }, { method: 'PUT', body: { expires_at: expiresAt }, idempotencyKey: key, signal }); }
/** owner/releaseId/reason为明确撤权目标，成功204才展示完成。 */
export function revokeGrant(owner: string, releaseId: string, reason: string, key: string, signal?: AbortSignal) { return requestJson(`/api/v1/admin/users/${uuid(owner)}/grants/${uuid(releaseId)}`, value => { if (value !== undefined) throw new Error('Invalid revoke'); }, { method: 'DELETE', body: { reason }, idempotencyKey: key, signal }); }
