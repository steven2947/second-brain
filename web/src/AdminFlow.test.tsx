// @vitest-environment jsdom
/** 自编HTTP响应验证管理身份页面；真实OTP与权限由后端PostgreSQL测试验证。 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { ProductApp } from './ProductApp';
import { readAdmin, reauthAdmin } from './api/admin';
import type { AdminIdentity } from './api/admin';

const id = '00000000-0000-0000-0000-000000000001', other = '00000000-0000-0000-0000-000000000002';
let identity: AdminIdentity, calls: { path: string; init: RequestInit }[], handler: (path: string, init: RequestInit) => Response;
/** path/init为当前请求，只有自编身份接口，不伪装业务发布能力。 */
function normal(path: string, _init: RequestInit): Response {
  if (path.endsWith('/csrf')) return Response.json({ csrf_token: 'admin-test-csrf' });
  if (path.endsWith('/logout')) return new Response(null, { status: 204 });
  return Response.json(identity);
}
beforeEach(() => {
  identity = { user: { id, email: 'curator@example.test', display_name: '自编管理员' }, granted_permissions: ['knowledge.import', 'knowledge.review'], verified_at: '2026-09-08T12:00:00Z', fresh_until: '2026-09-08T12:05:00Z', session_expires_at: '2026-09-08T20:00:00Z' };
  calls = []; handler = normal;
  vi.stubGlobal('fetch', vi.fn((path: string, init: RequestInit) => { calls.push({ path, init }); return Promise.resolve(handler(path, init)); }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
/** path仅含管理路由，不将登录信息传入URL/history。 */
function open(path = '/admin/login') { window.history.replaceState(null, '', path); return render(<ProductApp />); }

test('独立管理员入口一次提交密码与OTP，成功后展示实际权限', async () => {
  open(); fireEvent.change(screen.getByLabelText('管理员邮箱'), { target: { value: 'curator@example.test' } }); fireEvent.change(screen.getByLabelText('管理员密码'), { target: { value: 'Real-Form-Password-538!' } }); fireEvent.change(screen.getByLabelText('动态验证码'), { target: { value: '123456' } });
  await userEvent.click(screen.getByRole('button', { name: '验证并进入管理' })); await screen.findByRole('heading', { name: '自编管理员' });
  const writes = calls.filter(call => call.init.method === 'POST'); expect(writes).toHaveLength(1); expect(writes[0].path).toBe('/api/v1/admin/auth/login');
  expect(JSON.parse(String(writes[0].init.body))).toEqual({ email: 'curator@example.test', password: 'Real-Form-Password-538!', token: '123456', method: 'totp' });
  expect(new Headers(writes[0].init.headers).get('X-CSRFToken')).toBe('admin-test-csrf');
  expect(screen.getByText('导入知识版本')).toBeTruthy(); expect(screen.queryByText('禁用普通账号')).toBeNull();
  expect(calls.some(call => call.path.includes('/users') || call.path.includes('/problems'))).toBe(false);
  expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0); expect(JSON.stringify(window.history.state)).not.toContain('123456');
});
test('失败后密码验证码清空，不自动重试且不提示账号是否存在', async () => {
  handler = (path, init) => path.endsWith('/login') ? Response.json({ error: { code: 'INVALID_CREDENTIALS' } }, { status: 401 }) : normal(path, init);
  open(); fireEvent.change(screen.getByLabelText('管理员邮箱'), { target: { value: 'curator@example.test' } }); fireEvent.change(screen.getByLabelText('管理员密码'), { target: { value: 'bad-password' } }); fireEvent.change(screen.getByLabelText('动态验证码'), { target: { value: '000000' } });
  await userEvent.click(screen.getByRole('button', { name: '验证并进入管理' })); await screen.findByRole('alert');
  expect((screen.getByLabelText('管理员密码') as HTMLInputElement).value).toBe(''); expect((screen.getByLabelText('动态验证码') as HTMLInputElement).value).toBe(''); expect(calls.filter(call => call.init.method === 'POST')).toHaveLength(1);
});
test('切换到恢复码清除动态码，恢复码隐藏且只明确提交一次', async () => {
  open(); fireEvent.change(screen.getByLabelText('动态验证码'), { target: { value: '123456' } }); fireEvent.change(screen.getByLabelText('验证方式'), { target: { value: 'recovery' } });
  const recovery = screen.getByLabelText('恢复码') as HTMLInputElement; expect(recovery.value).toBe(''); expect(recovery.type).toBe('password');
  fireEvent.change(screen.getByLabelText('管理员邮箱'), { target: { value: 'curator@example.test' } }); fireEvent.change(screen.getByLabelText('管理员密码'), { target: { value: 'Real-Form-Password-538!' } }); fireEvent.change(recovery, { target: { value: 'self-authored-recovery' } });
  await userEvent.click(screen.getByRole('button', { name: '验证并进入管理' })); await screen.findByRole('heading', { name: '自编管理员' });
  expect(JSON.parse(String(calls.find(call => call.path.endsWith('/login'))!.init.body)).method).toBe('recovery'); expect(screen.queryByDisplayValue('self-authored-recovery')).toBeNull();
});
test('重新认证只验证当前管理员，退出后回到独立登录', async () => {
  open('/admin'); await screen.findByRole('heading', { name: '自编管理员' });
  fireEvent.change(screen.getByLabelText('再次输入密码'), { target: { value: 'Reauth-Password-987!' } }); fireEvent.change(screen.getByLabelText('动态验证码'), { target: { value: '654321' } }); await userEvent.click(screen.getByRole('button', { name: '重新验证管理身份' })); await screen.findByText('已重新验证身份。');
  expect(JSON.parse(String(calls.find(call => call.path.endsWith('/reauth'))!.init.body))).toEqual({ password: 'Reauth-Password-987!', token: '654321', method: 'totp' }); expect((screen.getByLabelText('再次输入密码') as HTMLInputElement).value).toBe('');
  await userEvent.click(screen.getByRole('button', { name: '退出管理' })); await screen.findByRole('heading', { name: '验证身份，再进入管理。' }); expect(window.location.pathname).toBe('/admin/login');
});
test('隐藏清理管理身份与敏感输入，恢复时重新验证而不保留旧权限', async () => {
  open('/admin'); await screen.findByRole('heading', { name: '自编管理员' }); fireEvent.change(screen.getByLabelText('再次输入密码'), { target: { value: 'unsubmitted-secret' } });
  fireEvent(window, new Event('pagehide')); expect(screen.queryByText('自编管理员')).toBeNull(); expect(screen.queryByDisplayValue('unsubmitted-secret')).toBeNull();
  handler = (path, init) => path.endsWith('/me') ? Response.json({ error: { code: 'ADMIN_AUTH_REQUIRED' } }, { status: 401 }) : normal(path, init);
  fireEvent(window, new Event('pageshow')); await screen.findByRole('heading', { name: '验证身份，再进入管理。' }); expect(screen.queryByText('knowledge.import')).toBeNull();
});
test('后台API不能用未知权限、错误账号或损坏时效响应提升界面权限', async () => {
  handler = () => Response.json({ ...identity, granted_permissions: ['root.all'] }); await expect(readAdmin()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  handler = normal;
  identity.granted_permissions = []; identity.user.id = other; await expect(reauthAdmin(id, { password: 'fixture', token: '123456', method: 'totp' })).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  identity.fresh_until = 'invalid-date'; await expect(readAdmin()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
});
test('没有显式权限的管理员只看到无权限状态，不出现可执行管理按钮', async () => {
  identity.granted_permissions = []; open('/admin'); await screen.findByText('此账号尚未配置具体管理权限。');
  expect(screen.queryByRole('button', { name: '发布知识版本' })).toBeNull(); expect(screen.queryByRole('button', { name: '禁用普通账号' })).toBeNull();
  await waitFor(() => expect(calls).toHaveLength(1)); expect(calls[0].path).toBe('/api/v1/admin/me');
});
