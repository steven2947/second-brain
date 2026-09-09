// @vitest-environment jsdom
/** 自编HTTP响应验证运营表单，实际跨用户权限和并发由后端PG测试覆盖。 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { ProductApp } from './ProductApp';
import type { AdminIdentity } from './api/admin';

const owner = '00000000-0000-0000-0000-000000000002', delivery = '00000000-0000-0000-0000-000000000003';
let identity: AdminIdentity, calls: { path: string; init: RequestInit }[], respond: (path: string, init: RequestInit) => Response;
/** path/init是当前自编请求，返回明确时间范围的聚合，不返回聊天或令牌。 */
function normal(path: string, init: RequestInit): Response {
  if (path.endsWith('/csrf')) return Response.json({ csrf_token: 'fixture-csrf' });
  if (path.endsWith('/me')) return Response.json(identity);
  if (path.endsWith('/operations')) return Response.json({ period: '2026-09-01', run_counts: [{ status: 'succeeded', count: 6 }, { status: 'failed', count: 1 }], total_runs: 7 });
  if (path.endsWith('/summary')) return Response.json({ category_counts: [{ category: 'shallow', count: 2 }], total_feedback: 2 });
  if (path.endsWith('/invitations')) return Response.json({ delivery: 'local_capture', delivery_id: delivery, expires_at: '2026-09-15T00:00:00Z' }, { status: 201 });
  if (path.endsWith('/quota')) return Response.json({ owner_id: owner, period: '2026-09-01', limit_runs: init.method === 'PUT' ? JSON.parse(String(init.body)).limit_runs : 100, reserved_runs: 2, settled_runs: 6, revision: init.method === 'PUT' ? 4 : 3 });
  const user = { id: owner, email: 'reader@example.test', display_name: '自编读者', status: 'active' };
  if (path.endsWith('/status')) return Response.json({ ...user, status: JSON.parse(String(init.body)).status });
  if (path.endsWith('/users')) return Response.json({ items: [user], next_cursor: null });
  return Response.json({ error: { code: 'NOT_FOUND' } }, { status: 404 });
}
beforeEach(() => {
  identity = { user: { id: '00000000-0000-0000-0000-000000000001', email: 'admin@example.test', display_name: '运营管理员' }, granted_permissions: ['accounts.view', 'accounts.disable', 'accounts.invite', 'quota.manage', 'operations.view', 'feedback.review'], verified_at: '2026-09-08T00:00:00Z', fresh_until: '2026-09-08T00:05:00Z', session_expires_at: '2026-09-08T08:00:00Z' };
  calls = []; respond = normal; vi.stubGlobal('fetch', vi.fn((path: string, init: RequestInit) => { calls.push({ path, init }); return Promise.resolve(respond(path, init)); }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
/** 无参数；进入真实产品路由，等待当前管理身份边界完成。 */
async function open() { window.history.replaceState(null, '', '/admin/operations'); render(<ProductApp />); await screen.findByRole('heading', { name: '运营工作台' }); }
/** 无参数；明确查询账号，选择当前服务端返回的普通账号。 */
async function selectUser() { await userEvent.click(screen.getByRole('button', { name: '查询普通账号' })); await userEvent.click(await screen.findByRole('button', { name: /自编读者/ })); }

test('统计标明月度和历史范围，不自动读取账号或提交写操作', async () => {
  await open(); await screen.findByText('2026-09 · UTC 月度任务'); await screen.findByText('建议太浅');
  expect(calls.some(call => call.path.endsWith('/users'))).toBe(false); expect(calls.filter(call => call.init.method !== 'GET')).toHaveLength(0);
});
test('停用要求明确原因和确认，携带当前状态且不修改权限', async () => {
  await open(); await selectUser(); fireEvent.change(screen.getByLabelText('状态变更原因'), { target: { value: '自编停用测试' } });
  expect((screen.getByRole('button', { name: '停用账号' }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.click(screen.getByLabelText(/确认变更此普通账号/)); await userEvent.click(screen.getByRole('button', { name: '停用账号' })); await screen.findByText('账号已停用，原会话已失效。');
  const call = calls.find(call => call.path.endsWith('/status'))!; expect(JSON.parse(String(call.init.body))).toEqual({ status: 'disabled', expected_status: 'active', reason: '自编停用测试' }); expect(new Headers(call.init.headers).get('Idempotency-Key')).toBeTruthy();
});
test('额度显示已用与预留，拒绝低于占用的值并携带修订号', async () => {
  await open(); await selectUser(); await userEvent.click(screen.getByRole('button', { name: '读取本月额度' })); await screen.findByText('已结算 6 次 · 执行中预留 2 次');
  fireEvent.change(screen.getByLabelText('本月总次数上限'), { target: { value: '7' } }); expect((screen.getByRole('button', { name: '保存本月额度' }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('本月总次数上限'), { target: { value: '50' } }); await userEvent.click(screen.getByRole('button', { name: '保存本月额度' })); await screen.findByText('本月次数额度已保存。');
  expect(JSON.parse(String(calls.find(call => call.init.method === 'PUT')!.init.body))).toEqual({ limit_runs: 50, expected_revision: 3, expected_period: '2026-09-01' });
});
test('邀请仅显示本机投递编号，不声称发送邮件或暴露令牌', async () => {
  await open(); fireEvent.change(screen.getByLabelText('邀请邮箱'), { target: { value: 'new@example.test' } }); await userEvent.click(screen.getByRole('button', { name: '生成本机邀请' })); await screen.findByText(delivery);
  expect(screen.getByText(/未发送邮件/)).toBeTruthy(); expect(calls.filter(call => call.path.endsWith('/invitations'))).toHaveLength(1); expect(localStorage.length).toBe(0);
});
test('只有额度权限可手动指定UUID，不查询账号和其他统计', async () => {
  identity.granted_permissions = ['quota.manage']; await open(); expect(screen.queryByRole('button', { name: '查询普通账号' })).toBeNull(); expect(screen.queryByLabelText('状态变更原因')).toBeNull();
  fireEvent.change(screen.getByLabelText('目标普通账号 ID'), { target: { value: owner } }); await userEvent.click(screen.getByRole('button', { name: '选择此账号' })); await userEvent.click(screen.getByRole('button', { name: '读取本月额度' })); await screen.findByText('已结算 6 次 · 执行中预留 2 次');
  expect(calls.some(call => call.path.endsWith('/users') || call.path.endsWith('/operations') || call.path.endsWith('/summary'))).toBe(false);
});
test('状态冲突保留原因不自动重发，隐藏页面清掉已选账号与草稿', async () => {
  respond = (path, init) => path.endsWith('/status') ? Response.json({ error: { code: 'STATUS_CONFLICT' } }, { status: 409 }) : normal(path, init);
  await open(); await selectUser(); fireEvent.change(screen.getByLabelText('状态变更原因'), { target: { value: '未提交完的原因' } }); await userEvent.click(screen.getByLabelText(/确认变更此普通账号/)); await userEvent.click(screen.getByRole('button', { name: '停用账号' })); await screen.findByRole('alert');
  expect(screen.getByDisplayValue('未提交完的原因')).toBeTruthy(); await waitFor(() => expect(calls.filter(call => call.path.endsWith('/status'))).toHaveLength(1));
  fireEvent(window, new Event('pagehide')); expect(screen.queryByDisplayValue('未提交完的原因')).toBeNull(); expect(screen.queryByRole('heading', { name: '运营工作台' })).toBeNull();
});
