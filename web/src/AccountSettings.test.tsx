// @vitest-environment jsdom
/** 已有账号接口的真实前端接线；不模拟后端会话失效证明。 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { ProductApp } from './ProductApp';
const account = { id: '11111111-1111-4111-8111-111111111111', email: 'reader@example.test', display_name: '自编读者', theme: 'system', timezone: 'Asia/Shanghai', email_verified_at: null, created_at: '2026-09-08T00:00:00Z' };
let calls: { path: string; init: RequestInit }[], failPassword: boolean, unauthorized: boolean;
beforeEach(() => { calls = []; failPassword = false; unauthorized = false; vi.stubGlobal('fetch', vi.fn(async (path: string, init: RequestInit) => {
  calls.push({ path, init });
  if (path.endsWith('/csrf')) return Response.json({ csrf_token: 'fixture-csrf' });
  if (path.endsWith('/options')) return Response.json({ password: { min_length: 12, max_length: 256 }, password_reset: { available: false, delivery: 'disabled', token_ttl_seconds: 1800 } });
  if (path.endsWith('/me')) return unauthorized ? Response.json({ error: { code: 'AUTH_REQUIRED' } }, { status: 401 }) : Response.json({ user: init.method === 'PATCH' ? { ...account, ...JSON.parse(String(init.body)) } : account });
  if (failPassword) return Response.json({ error: { code: 'INVALID_CREDENTIALS' } }, { status: 401 });
  return new Response(null, { status: 204 });
})); window.history.replaceState(null, '', '/app/settings'); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
/** 无参数；等待真实身份读取后展示设置，不预置登录状态。 */
async function open() { render(<ProductApp />); await screen.findByLabelText('修改称呼'); }
test('修改称呼只提交公开字段，成功更新当前账号显示', async () => {
  await open(); fireEvent.change(screen.getByLabelText('修改称呼'), { target: { value: '新称呼' } }); await userEvent.click(screen.getByRole('button', { name: '保存称呼' })); await screen.findByText('称呼已保存。'); const request = calls.find(call => call.init.method === 'PATCH')!; expect(request.path).toBe('/api/v1/me'); expect(JSON.parse(String(request.init.body))).toEqual({ display_name: '新称呼' }); expect(screen.getByText('新称呼', { selector: 'dd' })).toBeTruthy();
});
test('改密保留首尾空白，成功清空三个密码输入，不假称全退出', async () => {
  await open(); await waitFor(() => expect(screen.getByText(/12 至 256 个字符/)).toBeTruthy());
  fireEvent.change(screen.getByLabelText('当前密码'), { target: { value: '  old-password  ' } }); fireEvent.change(screen.getByLabelText('新密码'), { target: { value: '  New-Library-Password!  ' } }); fireEvent.change(screen.getByLabelText('再次输入新密码'), { target: { value: '  New-Library-Password!  ' } }); await userEvent.click(screen.getByRole('button', { name: '更新密码' })); await screen.findByText(/密码已更新，当前会话保留/);
  expect(JSON.parse(String(calls.find(call => call.path.endsWith('/me/password'))!.init.body))).toEqual({ current_password: '  old-password  ', new_password: '  New-Library-Password!  ' }); expect((screen.getByLabelText('当前密码') as HTMLInputElement).value).toBe(''); expect((screen.getByLabelText('新密码') as HTMLInputElement).value).toBe(''); expect((screen.getByLabelText('再次输入新密码') as HTMLInputElement).value).toBe('');
});
test('全退出必须本人密码和确认，204后才回登录', async () => {
  await open(); expect((screen.getByRole('button', { name: '退出所有设备' }) as HTMLButtonElement).disabled).toBe(true); fireEvent.change(screen.getByLabelText('全退出验证密码'), { target: { value: 'fixture-password' } }); await userEvent.click(screen.getByLabelText(/包括当前设备也会退出/)); await userEvent.click(screen.getByRole('button', { name: '退出所有设备' })); await waitFor(() => expect(window.location.pathname).toBe('/login')); expect(JSON.parse(String(calls.find(call => call.path.endsWith('/logout-all'))!.init.body))).toEqual({ password: 'fixture-password' });
});
test('密码重验失败清空输入但不把有效会话误判为退出', async () => {
  failPassword = true; await open(); fireEvent.change(screen.getByLabelText('全退出验证密码'), { target: { value: 'wrong' } }); await userEvent.click(screen.getByLabelText(/包括当前设备也会退出/)); await userEvent.click(screen.getByRole('button', { name: '退出所有设备' })); await screen.findByText(/当前密码验证未通过/); expect(window.location.pathname).toBe('/app/settings'); expect((screen.getByLabelText('全退出验证密码') as HTMLInputElement).value).toBe('');
});
test('隐藏移除全部设置草稿，恢复先重新验证身份', async () => {
  await open(); fireEvent.change(screen.getByLabelText('当前密码'), { target: { value: 'unsent-private' } }); fireEvent(window, new Event('pagehide')); expect(screen.queryByDisplayValue('unsent-private')).toBeNull(); expect(screen.queryByLabelText('修改称呼')).toBeNull(); unauthorized = true; fireEvent(window, new Event('pageshow')); await waitFor(() => expect(window.location.pathname).toBe('/login'));
});
