// @vitest-environment jsdom
/** 自编接口响应检查隐私交互，真实过期、撤权和物理清理由PG回归证明。 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { ProductApp } from './ProductApp';
import { MemoryRouter } from 'react-router-dom';
import { TrashProblemControl } from './features/privacy/Retention';

const id = '00000000-0000-0000-0000-000000000001', now = '2026-09-08T00:00:00Z';
let calls: { path: string; init: RequestInit }[], handler: (path: string, init: RequestInit) => Response, exported: boolean;
/** path/init为测试请求；只使用公开自编身份和个人记录元数据。 */
function normal(path: string, init: RequestInit): Response {
  if (path.endsWith('/csrf')) return Response.json({ csrf_token: 'privacy-test-csrf' });
  if (path.endsWith('/me')) return Response.json({ user: { id, email: 'reader@example.test', display_name: '自编读者', theme: 'system', timezone: 'Asia/Shanghai', email_verified_at: null, created_at: now } });
  const metadata = { id, scope: 'all_personal', status: 'ready', created_at: now, expires_at: '2026-09-09T00:00:00Z', error_code: null };
  if (path.endsWith('/exports') && init.method === 'POST') { exported = true; return Response.json(metadata, { status: 202 }); }
  if (path.includes('/exports?')) return Response.json({ items: exported ? [metadata] : [], next_cursor: null });
  if (path.endsWith('/download')) return Response.json({ schema_version: 1, export_id: id, scope: 'all_personal', generated_at: now, profile: { display_name: '自编读者' }, problems: [] });
  if (path.endsWith('/deletion')) return Response.json({ id, status: 'pending', requested_at: now, purge_after: '2026-09-15T00:00:00Z' }, { status: 202 });
  if (path.includes('/trash?')) return Response.json({ items: [{ id, title: '自编已删除问题', status: 'deleted', revision: 4, deleted_at: now, purge_after: '2026-10-08T00:00:00Z' }], next_cursor: null });
  if (path.endsWith('/restore')) return Response.json({ id, title: '自编已删除问题', original_question: '自编原问题', goal: 'analyze', release_id: id, revision: 5, status: 'archived', clarification: { rounds: 0, limit: 5, pending_question: null, closed: false }, current_answer_id: null, library_available: false, created_at: now, updated_at: now });
  return Response.json({ error: { code: 'NOT_FOUND' } }, { status: 404 });
}
beforeEach(() => { exported = false; calls = []; handler = normal; vi.stubGlobal('fetch', vi.fn((path: string, init: RequestInit) => { calls.push({ path, init }); return Promise.resolve(handler(path, init)); })); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
/** path为隐私或回收站路由；不将私有内容放入URL。 */
async function open(path = '/app/privacy') { window.history.replaceState(null, '', path); render(<ProductApp />); await screen.findByRole('heading', { name: path.endsWith('trash') ? '问题回收站' : '隐私与数据' }); }

test('页面明确导出与删除保留规则，不自动发起任务或下载', async () => {
  await open(); await screen.findByText('还没有导出记录。'); expect(screen.getByText(/完成后 24 小时内/)).toBeTruthy(); expect(screen.getByText(/7 天冷静期/)).toBeTruthy(); expect(calls.filter(call => call.init.method !== 'GET')).toHaveLength(0);
});
test('再次认证后显式申请导出，密码提交后清空，不写入幂等签名或浏览器存储', async () => {
  await open(); fireEvent.change(screen.getByLabelText('导出前验证密码'), { target: { value: 'SelfAuthored-Privacy-Password!' } }); await userEvent.click(screen.getByRole('button', { name: '生成个人数据导出' })); await screen.findByRole('button', { name: '下载 JSON 文件' });
  const writes = calls.filter(call => call.init.method === 'POST'); expect(writes).toHaveLength(1); expect(JSON.parse(String(writes[0].init.body))).toEqual({ scope: 'all_personal', password: 'SelfAuthored-Privacy-Password!' }); expect(new Headers(writes[0].init.headers).get('Idempotency-Key')).toBeTruthy(); expect((screen.getByLabelText('导出前验证密码') as HTMLInputElement).value).toBe(''); expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0);
});
test('注销必须确认后输入准确文字与密码，成功不冒充已物理删除', async () => {
  await open(); await userEvent.click(screen.getByText('了解并申请注销账号')); fireEvent.change(screen.getByLabelText('注销前验证密码'), { target: { value: 'SelfAuthored-Delete-Password!' } }); fireEvent.change(screen.getByLabelText('输入“删除我的账号”确认'), { target: { value: '删除' } }); expect((screen.getByRole('button', { name: '确认申请注销' }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('输入“删除我的账号”确认'), { target: { value: '删除我的账号' } }); await userEvent.click(screen.getByLabelText(/我理解账号将立即停止访问/)); await userEvent.click(screen.getByRole('button', { name: '确认申请注销' })); await screen.findByRole('heading', { name: '注销申请已受理' });
  expect(screen.getByText(/尚未立即物理删除/)).toBeTruthy(); expect(screen.queryByLabelText('导出前验证密码')).toBeNull(); expect(calls.filter(call => call.path.endsWith('/deletion'))).toHaveLength(1);
});
test('回收站恢复带修订号，恢复到归档并不承诺恢复知识权限', async () => {
  await open('/app/trash'); await screen.findByText('自编已删除问题'); await userEvent.click(screen.getByRole('button', { name: '恢复为归档问题' })); await screen.findByText(/已恢复到归档/);
  expect(JSON.parse(String(calls.find(call => call.path.endsWith('/restore'))!.init.body))).toEqual({ expected_revision: 4 }); expect(screen.getByText(/删除后 30 天内可恢复.*不会恢复知识授权/)).toBeTruthy();
});
test('写请求失败清密码，同范围手动重试沿用幂等键，不自动重发', async () => {
  handler = (path, init) => path.endsWith('/exports') && init.method === 'POST' ? Response.json({ error: { code: 'TEMPORARY_FAILURE' } }, { status: 503 }) : normal(path, init);
  await open(); fireEvent.change(screen.getByLabelText('导出前验证密码'), { target: { value: 'SelfAuthored-Privacy-Password!' } }); await userEvent.click(screen.getByRole('button', { name: '生成个人数据导出' })); await screen.findByRole('alert'); expect((screen.getByLabelText('导出前验证密码') as HTMLInputElement).value).toBe(''); expect(calls.filter(call => call.init.method === 'POST')).toHaveLength(1);
  handler = normal; fireEvent.change(screen.getByLabelText('导出前验证密码'), { target: { value: 'SelfAuthored-Privacy-Password!' } }); await userEvent.click(screen.getByRole('button', { name: '生成个人数据导出' })); await screen.findByRole('button', { name: '下载 JSON 文件' }); const writes = calls.filter(call => call.init.method === 'POST'); expect(new Headers(writes[0].init.headers).get('Idempotency-Key')).toBe(new Headers(writes[1].init.headers).get('Idempotency-Key'));
});
test('隐藏立即销毁密码、确认文本和个人导出列表，恢复重读身份', async () => {
  exported = true; await open(); await screen.findByRole('button', { name: '下载 JSON 文件' }); fireEvent.change(screen.getByLabelText('导出前验证密码'), { target: { value: 'private-unsent' } }); fireEvent(window, new Event('pagehide')); expect(screen.queryByDisplayValue('private-unsent')).toBeNull(); expect(screen.queryByRole('button', { name: '下载 JSON 文件' })).toBeNull();
  handler = (path, init) => path.endsWith('/me') ? Response.json({ error: { code: 'AUTH_REQUIRED' } }, { status: 401 }) : normal(path, init); fireEvent(window, new Event('pageshow')); await waitFor(() => expect(window.location.pathname).toBe('/login'));
});

test('下载每次重新请求受控接口，不暴露长期链接，释放临时Blob引用', async () => {
  exported = true; const create = vi.fn(() => 'blob:privacy-fixture'), revoke = vi.fn(), click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  vi.stubGlobal('URL', class extends URL { static createObjectURL = create; static revokeObjectURL = revoke; });
  await open(); await userEvent.click(await screen.findByRole('button', { name: '下载 JSON 文件' })); await screen.findByText(/文件已交给浏览器下载/); await waitFor(() => expect(revoke).toHaveBeenCalledWith('blob:privacy-fixture'));
  expect(calls.filter(call => call.path.endsWith('/download'))).toHaveLength(1); expect(create).toHaveBeenCalledOnce(); expect(click).toHaveBeenCalledOnce(); expect(document.querySelector('a[href^="blob:"]')).toBeNull();
});
test('下载已撤权不会创建Blob或伪装保存成功', async () => {
  exported = true; const create = vi.fn(); vi.stubGlobal('URL', class extends URL { static createObjectURL = create; });
  handler = (path, init) => path.endsWith('/download') ? Response.json({ error: { code: 'EXPORT_UNAVAILABLE' } }, { status: 404 }) : normal(path, init);
  await open(); await userEvent.click(await screen.findByRole('button', { name: '下载 JSON 文件' })); await screen.findByRole('alert'); expect(create).not.toHaveBeenCalled(); expect(screen.queryByText(/文件已交给浏览器下载/)).toBeNull();
});
test.each([
  ['EXPORT_STALE', 409, '原记录或知识权限已变化，请重新申请导出。'],
  ['EXPORT_TOO_LARGE', 413, '导出超过单次容量，请改选问题或学习记录；若仍失败，请联系管理员。'],
  ['EXPORT_LIMIT', 429, '已有多个导出任务处理中，请等它们结束后再申请。'],
])('导出失败 %s 给出准确下一步，不建议无效重试', async (code, status, message) => {
  handler = (path, init) => path.endsWith('/exports') && init.method === 'POST' ? Response.json({ error: { code } }, { status }) : normal(path, init);
  await open(); fireEvent.change(screen.getByLabelText('导出前验证密码'), { target: { value: 'SelfAuthored-Privacy-Password!' } }); await userEvent.click(screen.getByRole('button', { name: '生成个人数据导出' }));
  expect((await screen.findByRole('alert')).textContent).toBe(message); expect(calls.filter(call => call.init.method === 'POST')).toHaveLength(1);
});
test('超过回收期限明确不可恢复，不提示刷新重试', async () => {
  handler = (path, init) => path.endsWith('/restore') ? Response.json({ error: { code: 'TRASH_EXPIRED' } }, { status: 410 }) : normal(path, init);
  await open('/app/trash'); await userEvent.click(await screen.findByRole('button', { name: '恢复为归档问题' }));
  expect((await screen.findByRole('alert')).textContent).toBe('这个问题已超过 30 天恢复期限，无法再恢复。'); expect(screen.queryByText(/已恢复到归档/)).toBeNull();
});
test('问题删除控件需要确认，只发送当前revision的DELETE不直接清理', async () => {
  handler = (path, init) => path === `/api/v1/problems/${id}` && init.method === 'DELETE' ? new Response(null, { status: 204 }) : normal(path, init);
  render(<MemoryRouter><TrashProblemControl id={id} revision={4} disabled={false} onFailure={vi.fn()} /></MemoryRouter>); await userEvent.click(screen.getByText('删除这个问题')); expect((screen.getByRole('button', { name: '移入回收站' }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.click(screen.getByLabelText('确认将这个问题移入回收站')); await userEvent.click(screen.getByRole('button', { name: '移入回收站' })); await waitFor(() => expect(calls.some(call => call.init.method === 'DELETE')).toBe(true)); const deletion = calls.find(call => call.init.method === 'DELETE')!; expect(JSON.parse(String(deletion.init.body))).toEqual({ expected_revision: 4 }); expect(new Headers(deletion.init.headers).get('X-CSRFToken')).toBeTruthy();
});
