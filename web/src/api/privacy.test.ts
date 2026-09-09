/** 隐私接口白名单、归属与下载格式测试；不包含实际用户导出文件。 */
import { afterEach, expect, test, vi } from 'vitest';
import { downloadExport, readExport, readTrash, requestDeletion, requestExport } from './privacy';
const id = '00000000-0000-0000-0000-000000000001', other = '00000000-0000-0000-0000-000000000002', date = '2026-09-08T00:00:00Z';
const metadata = { id, scope: 'all_personal', status: 'ready', created_at: date, expires_at: '2026-09-09T00:00:00Z', error_code: null };
/** data为测试响应，CSRF仍独立读取；记录实际请求验证敏感输入没有进入URL。 */
function reply(data: unknown) { const fetch = vi.fn(async (path: string) => Response.json(path.endsWith('/csrf') ? { csrf_token: 'fixture' } : data)); vi.stubGlobal('fetch', fetch); return fetch; }
afterEach(() => vi.unstubAllGlobals());
test('导出任务拒绝错ID/缺有效期/未知状态，多余字段不留在元数据', async () => {
  for (const changes of [{ id: other }, { expires_at: null }, { status: 'pretend_ready' }]) { reply({ ...metadata, ...changes }); await expect(readExport(id)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' }); }
  reply({ ...metadata, storage_key: 'never-retain', password: 'never-retain' }); expect(await readExport(id)).toEqual(metadata);
});
test('JSON下载必须匹配导出ID、范围与格式版本，不能把错误文件交给用户', async () => {
  const payload = { schema_version: 1, export_id: id, scope: 'all_personal', generated_at: date, problems: [] };
  for (const changes of [{ export_id: other }, { scope: 'learning' }, { schema_version: 2 }, { generated_at: 'invalid' }]) { reply({ ...payload, ...changes }); await expect(downloadExport(id, 'all_personal')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' }); }
  reply(payload); const result = await downloadExport(id, 'all_personal'); expect(result.type).toBe('application/json'); expect(JSON.parse(await result.text())).toEqual(payload);
});
test('回收站只收删除状态、有效时刻和唯一ID，不传播正文', async () => {
  const record = { id, title: '自编问题', status: 'deleted', revision: 2, deleted_at: date, purge_after: '2026-10-08T00:00:00Z' };
  reply({ items: [{ ...record, core_state: { never: 'retain' } }], next_cursor: null }); expect(await readTrash()).toEqual({ items: [record], next_cursor: null });
  reply({ items: [record, record], next_cursor: null }); await expect(readTrash()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
});
test('敏感密码只在明确POST body，创建导出带幂等，注销只接受pending回执', async () => {
  const fetch = reply(metadata); await requestExport('all_personal', 'fixture-password', 'export-fixture'); const [path, init] = fetch.mock.calls[1] as unknown as [string, RequestInit]; expect(path).toBe('/api/v1/me/exports'); expect(new Headers(init.headers).get('Idempotency-Key')).toBe('export-fixture'); expect(JSON.parse(String(init.body))).toEqual({ scope: 'all_personal', password: 'fixture-password' });
  reply({ id, status: 'completed', requested_at: date, purge_after: date }); await expect(requestDeletion('fixture-password', '删除我的账号')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
});
