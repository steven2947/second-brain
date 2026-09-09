// @vitest-environment jsdom
/** 自编邮件能力和响应检查找回交互；实际令牌/邮件安全由后端PG测试验证。 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { ProductApp } from './ProductApp';
import { StrictMode } from 'react';

const token = 'self-authored-fixture-token', password = '  Library-Recovery-732!  ';
let calls: { path: string; init: RequestInit }[], mode: 'disabled' | 'local_capture' | 'smtp';
let handler: (path: string, init: RequestInit) => Response;
/** path/init为自编HTTP接缝；不提供真实邮箱或令牌。 */
function normal(path: string, init: RequestInit) {
  if (path.endsWith('/csrf')) return Response.json({ csrf_token: 'fixture-csrf' });
  if (path.endsWith('/options')) return Response.json({ password: { min_length: 12, max_length: 256 }, password_reset: { available: mode !== 'disabled', delivery: mode, token_ttl_seconds: 1800 } });
  if (path.endsWith('/request')) return Response.json({ status: 'accepted', delivery: mode }, { status: 202 });
  if (path.endsWith('/confirm') && init.method === 'POST') return new Response(null, { status: 204 });
  return Response.json({ error: { code: 'NOT_FOUND' } }, { status: 404 });
}
beforeEach(() => { calls = []; mode = 'smtp'; handler = normal; vi.stubGlobal('fetch', vi.fn((path: string, init: RequestInit) => { calls.push({ path, init }); return Promise.resolve(handler(path, init)); })); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
/** path为当前页面，fragment只用于一次性收取自编令牌。 */
function open(path = '/forgot-password') { window.history.replaceState(null, '', path); render(<StrictMode><ProductApp /></StrictMode>); }

test('未配置渠道明确不可用，不发送找回请求', async () => {
  mode = 'disabled'; open(); await screen.findByText(/当前未启用密码找回/); expect((screen.getByRole('button', { name: '申请重置链接' }) as HTMLButtonElement).disabled).toBe(true); expect(calls.some(call => call.init.method === 'POST')).toBe(false);
});
test('本机捕获明确不是发邮件，申请只带邮箱且结果不确认账号存在', async () => {
  mode = 'local_capture'; open(); await screen.findByText(/本机测试模式，不会发送到你的邮箱/); fireEvent.change(screen.getByLabelText('账号邮箱'), { target: { value: 'reader@example.test' } }); await userEvent.click(screen.getByRole('button', { name: '申请重置链接' })); await screen.findByText(/如账号符合条件，重置链接会交给本机测试捕获/);
  const request = calls.find(call => call.path.endsWith('/request'))!; expect(JSON.parse(String(request.init.body))).toEqual({ email: 'reader@example.test' }); expect(new Headers(request.init.headers).get('X-CSRFToken')).toBe('fixture-csrf'); expect(screen.queryByText(/邮件已发送/)).toBeNull();
});
test('SMTP的202只显示申请受理，不保证送达，不自动重发', async () => {
  open(); await screen.findByText(/链接有效期为 30 分钟/); fireEvent.change(screen.getByLabelText('账号邮箱'), { target: { value: 'reader@example.test' } }); await userEvent.click(screen.getByRole('button', { name: '申请重置链接' })); await screen.findByText(/如账号符合条件，我们会尝试发送重置邮件/); expect(calls.filter(call => call.path.endsWith('/request'))).toHaveLength(1);
});
test('fragment令牌从URL清除，确认后用原密码字符提交，成功要求重新登录', async () => {
  open('/reset-password#token=' + token); await screen.findByLabelText('确认新密码'); expect(window.location.hash).toBe(''); expect(window.location.search).toBe(''); expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0); expect(calls.some(call => call.path.includes(token))).toBe(false);
  fireEvent.change(screen.getByLabelText('密码', { exact: true }), { target: { value: password } }); fireEvent.change(screen.getByLabelText('确认新密码'), { target: { value: password } }); await userEvent.click(screen.getByRole('button', { name: '保存新密码' })); await screen.findByRole('heading', { name: '密码已更新' });
  expect(JSON.parse(String(calls.find(call => call.path.endsWith('/confirm'))!.init.body))).toEqual({ token, new_password: password }); expect(screen.getByRole('link', { name: '使用新密码登录' }).getAttribute('href')).toBe('/login'); expect(screen.queryByDisplayValue(password)).toBeNull(); expect(calls.filter(call => call.init.method === 'POST')).toHaveLength(1);
});
test('重复令牌或query令牌不采用，页面不出现可提交的重置表单', async () => {
  open('/reset-password?token=unsafe-query#token=one&token=two'); await screen.findByText(/链接缺失或已从当前页面清除/); expect(window.location.search).toBe(''); expect(window.location.hash).toBe(''); expect(screen.queryByRole('button', { name: '保存新密码' })).toBeNull();
});
test('密码不一致不发请求，过期链接失败清密码并给出重新申请入口', async () => {
  handler = (path, init) => path.endsWith('/confirm') ? Response.json({ error: { code: 'RESET_INVALID', message: 'private-server-message' } }, { status: 400 }) : normal(path, init);
  open('/reset-password#token=' + token); await screen.findByLabelText('确认新密码'); fireEvent.change(screen.getByLabelText('密码', { exact: true }), { target: { value: password } }); fireEvent.change(screen.getByLabelText('确认新密码'), { target: { value: 'different-password' } }); await userEvent.click(screen.getByRole('button', { name: '保存新密码' })); await screen.findByText('两次输入的密码不一致。'); expect(calls.some(call => call.path.endsWith('/confirm'))).toBe(false);
  fireEvent.change(screen.getByLabelText('确认新密码'), { target: { value: password } }); await userEvent.click(screen.getByRole('button', { name: '保存新密码' })); await screen.findByText(/重置链接已失效或不可用/); expect(screen.queryByText('private-server-message')).toBeNull(); expect(screen.queryByDisplayValue(password)).toBeNull();
});
test('隐藏页面清除令牌及密码，回来不能意外提交旧令牌', async () => {
  open('/reset-password#token=' + token); await screen.findByLabelText('确认新密码'); fireEvent.change(screen.getByLabelText('密码', { exact: true }), { target: { value: password } }); fireEvent(window, new Event('pagehide')); await screen.findByText(/链接缺失或已从当前页面清除/); expect(screen.queryByDisplayValue(password)).toBeNull(); expect(screen.queryByRole('button', { name: '保存新密码' })).toBeNull();
});
test('渠道失败不呈现受理成功，保留邮箱供手动重试', async () => {
  handler = (path, init) => path.endsWith('/request') ? Response.json({ error: { code: 'CHANNEL_UNAVAILABLE' } }, { status: 503 }) : normal(path, init);
  open(); await screen.findByLabelText('账号邮箱'); fireEvent.change(screen.getByLabelText('账号邮箱'), { target: { value: 'reader@example.test' } }); await waitFor(() => expect((screen.getByRole('button', { name: '申请重置链接' }) as HTMLButtonElement).disabled).toBe(false)); await userEvent.click(screen.getByRole('button', { name: '申请重置链接' })); await screen.findByText(/邮件渠道当前不可用/); expect(screen.queryByText(/如账号符合条件，我们会尝试发送重置邮件/)).toBeNull(); expect(screen.getByDisplayValue('reader@example.test')).toBeTruthy();
});
