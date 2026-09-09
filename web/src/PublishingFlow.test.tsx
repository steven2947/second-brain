// @vitest-environment jsdom
/** 自编响应验收管理交互，不替代真实PG授权、导入或版权核验。 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { ProductApp } from './ProductApp';
import type { AdminIdentity } from './api/admin';
import type { ReleaseDetail } from './api/publishing';
import { grantRelease, readManagedRelease, revokeGrant } from './api/publishing';

const admin = '00000000-0000-0000-0000-000000000001', releaseId = '00000000-0000-0000-0000-000000000002', userId = '00000000-0000-0000-0000-000000000003', jobId = '00000000-0000-0000-0000-000000000004';
let identity: AdminIdentity, release: ReleaseDetail, calls: { path: string; init: RequestInit }[], imported: boolean;
let respond: (path: string, init: RequestInit) => Response;
/** path/init是当前测试HTTP请求，只保存公开自编记录和真实提交载荷。 */
function normal(path: string, init: RequestInit): Response {
  if (path.endsWith('/csrf')) return Response.json({ csrf_token: 'test-publishing-csrf' });
  if (path.endsWith('/me')) return Response.json(identity);
  if (path.endsWith('/sources')) return Response.json({ items: [{ staging_key: 'self-authored', title: '自编试行库', content_version: 'a'.repeat(24), book_count: 1, card_count: 2 }] });
  if (path.endsWith('/releases/import')) { imported = true; return Response.json({ job_id: jobId }, { status: 202 }); }
  if (path.includes('/imports')) return Response.json({ items: imported ? [{ id: jobId, status: 'succeeded', stage: 'completed', release_id: releaseId, error_code: null }] : [], next_cursor: null });
  if (path.endsWith('/users')) return Response.json({ items: [{ id: userId, email: 'reader@example.test', display_name: '自编读者', status: 'active' }], next_cursor: null });
  if (path.includes('/grants/')) return init.method === 'DELETE' ? new Response(null, { status: 204 }) : Response.json({ id: jobId, owner_id: userId, release_id: releaseId, status: 'active', expires_at: null });
  if (path.endsWith('/rights')) { release.rights_status = 'approved'; return Response.json(release); }
  if (path.endsWith('/publish')) { release.status = 'published'; return Response.json(release); }
  if (path.endsWith('/revoke')) { release.status = 'revoked'; return Response.json(release); }
  if (path.endsWith('/releases')) return Response.json({ items: [release], next_cursor: null });
  if (path.endsWith(`/releases/${releaseId}`)) return Response.json(release);
  return Response.json({ error: { code: 'NOT_FOUND' } }, { status: 404 });
}
beforeEach(() => {
  identity = { user: { id: admin, email: 'admin@example.test', display_name: '自编管理' }, granted_permissions: ['knowledge.import', 'knowledge.review', 'knowledge.publish', 'knowledge.revoke', 'grants.manage', 'accounts.view'], verified_at: '2026-09-08T12:00:00Z', fresh_until: '2026-09-08T12:05:00Z', session_expires_at: '2026-09-08T20:00:00Z' };
  release = { id: releaseId, title: '自编试行库', description: '只供本地测试', content_version: 'a'.repeat(24), status: 'validated', rights_status: 'unreviewed', book_count: 1, card_count: 2, books: [{ id: 'book.sample', title: '可撤回的试行', author_display: '自编测试作者' }], rights_records: [] };
  calls = []; imported = false; respond = normal;
  vi.stubGlobal('fetch', vi.fn((path: string, init: RequestInit) => { calls.push({ path, init }); return Promise.resolve(respond(path, init)); }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
/** 无参数；进入受保护后台知识页，等待真实读请求完成。 */
async function open() { window.history.replaceState(null, '', '/admin/knowledge'); render(<ProductApp />); await screen.findByRole('heading', { name: '让知识有序进入书房。' }); await screen.findByRole('button', { name: /自编试行库.*技术通过/ }); }
/** 无参数；展开已返回的固定版本，等待作者与审核状态加载。 */
async function selectRelease() { await userEvent.click(screen.getByRole('button', { name: /自编试行库.*技术通过/ })); await screen.findByText('自编测试作者'); }

test('管理页真实分开技术与权利状态，书名带作者，未审核不能发布', async () => {
  await open(); await selectRelease(); expect(screen.getByText('可撤回的试行')).toBeTruthy();
  expect((screen.getByRole('button', { name: '发布知识版本' }) as HTMLButtonElement).disabled).toBe(true);
  expect(calls.filter(call => call.init.method !== 'GET')).toHaveLength(0); expect(calls.some(call => call.path.endsWith('/users'))).toBe(false);
});
test('显式导入从登记选项发送，结果只提示待审，不自动发布和授权', async () => {
  await open(); fireEvent.change(screen.getByLabelText('选择来源'), { target: { value: 'self-authored' } });
  await userEvent.click(screen.getByRole('button', { name: '开始技术导入' })); await screen.findByText('导入完成，仍需权利审核');
  const writes = calls.filter(call => call.init.method !== 'GET'); expect(writes).toHaveLength(1); expect(JSON.parse(String(writes[0].init.body))).toEqual({ staging_key: 'self-authored' });
  expect(new Headers(writes[0].init.headers).get('Idempotency-Key')).toBeTruthy(); expect(calls.some(call => call.path.endsWith('/publish') || call.path.includes('/grants/'))).toBe(false);
});
test('网络结果不明后手动重试沿用同一幂等键，没有自动重发', async () => {
  respond = (path, init) => { if (path.endsWith('/releases/import')) throw new TypeError('offline'); return normal(path, init); };
  await open(); fireEvent.change(screen.getByLabelText('选择来源'), { target: { value: 'self-authored' } }); await userEvent.click(screen.getByRole('button', { name: '开始技术导入' })); await screen.findByRole('alert');
  expect(calls.filter(call => call.init.method === 'POST')).toHaveLength(1); respond = normal;
  await userEvent.click(screen.getByRole('button', { name: '开始技术导入' })); await screen.findByText('导入完成，仍需权利审核');
  const writes = calls.filter(call => call.init.method === 'POST'); expect(writes).toHaveLength(2); expect(new Headers(writes[0].init.headers).get('Idempotency-Key')).toBe(new Headers(writes[1].init.headers).get('Idempotency-Key'));
});
test('审核用途与批准决定都需人工选择，PUT带CSRF和幂等，不伪造审核人', async () => {
  await open(); await selectRelease(); await userEvent.click(screen.getByText('填写 / 重审本版本权利记录'));
  expect((screen.getByLabelText('人工审核决定') as HTMLSelectElement).value).toBe(''); expect((screen.getByLabelText('知识浏览') as HTMLInputElement).checked).toBe(false);
  fireEvent.change(screen.getByLabelText('来源与依据说明'), { target: { value: '本测试内容由我们自行撰写。' } }); fireEvent.change(screen.getByLabelText('权利依据'), { target: { value: 'self_authored' } }); await userEvent.click(screen.getByLabelText('知识浏览')); await userEvent.click(screen.getByLabelText('用于分析与学习'));
  fireEvent.change(screen.getByLabelText('人工审核决定'), { target: { value: 'approved' } }); await userEvent.click(screen.getByLabelText(/我已核对完整记录集/)); await userEvent.click(screen.getByRole('button', { name: '保存人工审核记录' }));
  await waitFor(() => expect(calls.some(call => call.init.method === 'PUT')).toBe(true)); const call = calls.find(call => call.init.method === 'PUT')!;
  expect(JSON.parse(String(call.init.body))).toEqual({ records: [{ scope_book_ids: [], source_description: '本测试内容由我们自行撰写。', basis_type: 'self_authored', license_name: null, proof_storage_key: null, allowed_audience: 'granted_users', allowed_uses: ['browse', 'analyze'], quote_policy: {}, valid_until: null, status: 'approved' }] });
  expect(new Headers(call.init.headers).get('X-CSRFToken')).toBeTruthy(); expect(new Headers(call.init.headers).get('Idempotency-Key')).toBeTruthy();
});
test('先确认再发布，发布不替用户自动开通知识权限', async () => {
  release.rights_status = 'approved'; await open(); await selectRelease(); expect((screen.getByRole('button', { name: '发布知识版本' }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.click(screen.getByLabelText(/我已核对本版本的书籍范围/)); await userEvent.click(screen.getByRole('button', { name: '发布知识版本' })); await screen.findByText(/该版本已发布/);
  const writes = calls.filter(call => call.init.method !== 'GET'); expect(writes).toHaveLength(1); expect(JSON.parse(String(writes[0].init.body))).toEqual({ expected_status: 'validated' });
});
test('缺少导入或授权权限不请求来源和账号，隐藏页面清除审核草稿', async () => {
  identity.granted_permissions = ['knowledge.review']; await open(); await selectRelease(); expect(screen.queryByRole('button', { name: '开始技术导入' })).toBeNull(); expect(screen.queryByText('目标普通账号 ID')).toBeNull();
  expect(calls.some(call => call.path.endsWith('/sources') || call.path.endsWith('/users'))).toBe(false);
  await userEvent.click(screen.getByText('填写 / 重审本版本权利记录')); fireEvent.change(screen.getByLabelText('来源与依据说明'), { target: { value: '私有未提交依据' } }); fireEvent(window, new Event('pagehide'));
  expect(screen.queryByDisplayValue('私有未提交依据')).toBeNull(); expect(screen.queryByText('自编测试作者')).toBeNull(); expect(localStorage.length).toBe(0);
});
test('接口拒绝错误版本与错发给另一个账号的授权，DELETE使用同源CSRF与幂等', async () => {
  respond = () => Response.json({ ...release, id: userId }); await expect(readManagedRelease(releaseId)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  respond = (path, init) => path.includes('/grants/') ? Response.json({ id: jobId, owner_id: admin, release_id: releaseId, status: 'active', expires_at: null }) : normal(path, init);
  await expect(grantRelease(userId, releaseId, null, 'grant-1')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' }); respond = normal;
  await revokeGrant(userId, releaseId, '管理员明确撤销', 'revoke-1'); const call = calls.find(call => call.init.method === 'DELETE')!; expect(new Headers(call.init.headers).get('Idempotency-Key')).toBe('revoke-1'); expect(new Headers(call.init.headers).get('X-CSRFToken')).toBeTruthy();
});
