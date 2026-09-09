// @vitest-environment jsdom
/** 通过真实组件与fetch传输接缝验证认证流程；不替换业务函数。 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProductApp } from './ProductApp';

const user = { id: '11111111-1111-4111-8111-111111111111', email: 'reader@example.test', display_name: '林间读者',
  timezone: 'Asia/Shanghai', theme: 'system', email_verified_at: null, created_at: '2026-09-08T00:00:00Z' };
const options = { registration: { enabled: true, invitation_required: true,
  policy_versions: { terms: 'local-test-current', privacy: 'local-test-current' },
  policies: [{ kind: 'terms', title: '本机测试服务说明', body: '仅用于本机验证账号流程。', version: 'local-test-current', test_only: true },
    { kind: 'privacy', title: '本机测试隐私说明', body: '测试数据仅用于本机开发验证。', version: 'local-test-current', test_only: true }] },
  password: { min_length: 12, max_length: 256 }, password_reset: { available: false, delivery: 'disabled', token_ttl_seconds: 1800 }, admin_mfa: { available: false } };
type FetchCall = { path: string; init?: RequestInit };
let calls: FetchCall[];
let respond: (path: string, init?: RequestInit) => Response | Promise<Response>;
/** value/status/headers为真实HTTP模拟响应数据。 */
const json = (value: unknown, status = 200, headers?: HeadersInit) => new Response(JSON.stringify(value), { status, headers });
/** code/status为固定公开错误；自由文本故意含秘密，验证页面不会回显。 */
const failure = (code: string, status = 401, headers?: HeadersInit) => json({ error: { code, message: 'REMOTE SECRET', request_id: '22222222-2222-4222-8222-222222222222' } }, status, headers);
/** path为当前浏览器路由，初始状态不含任何敏感数据。 */
function open(path = '/login') { window.history.replaceState(null, '', path); return render(<ProductApp />); }
/** 无参数；输入真实登录表单，密码首尾空白必须保留。 */
async function fillLogin() {
  const keyboard = userEvent.setup();
  await keyboard.type(screen.getByLabelText('邮箱'), user.email);
  await keyboard.type(screen.getByLabelText('密码', { exact: true }), '  Forest-River-482!  ');
  return keyboard;
}
/** 无参数；填完整注册输入，政策必须单独勾选。 */
async function fillRegistration() {
  const keyboard = userEvent.setup();
  await screen.findByText('本机测试服务说明');
  await keyboard.type(screen.getByLabelText('邀请码'), 'private-invitation');
  await keyboard.type(screen.getByLabelText('称呼'), user.display_name);
  await keyboard.type(screen.getByLabelText('邮箱'), user.email);
  await keyboard.type(screen.getByLabelText('密码', { exact: true }), '  Forest-River-482!  ');
  return keyboard;
}
beforeEach(() => {
  calls = [];
  respond = path => path.endsWith('/options') ? json(options) : path.endsWith('/csrf') ? json({ csrf_token: 'realistic-test-csrf' }) : path.endsWith('/me') ? json({ user }) : json({ user });
  vi.stubGlobal('fetch', vi.fn((path: string, init?: RequestInit) => { calls.push({ path, init }); return Promise.resolve(respond(path, init)); }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe('登录与公开页面', () => {
  it('登录成功使用真实写请求，保留密码空白并进入真实账号页', async () => {
    open('/login?next=https://evil.example');
    const keyboard = await fillLogin();
    await keyboard.click(screen.getByRole('button', { name: '登录' }));
    await screen.findByRole('heading', { name: '你好，林间读者' });
    expect(window.location.pathname).toBe('/app');
    expect(JSON.parse(calls.find(call => call.path.endsWith('/login'))!.init!.body as string).password).toBe('  Forest-River-482!  ');
    expect(screen.getByText('邮箱尚未验证')).toBeTruthy();
    expect(screen.getByRole('link', { name: '进入知识库' }).getAttribute('href')).toBe('/app/library');
  });

  it('失败清除密码、保留邮箱，只显示固定错误与安全请求号', async () => {
    respond = path => path.endsWith('/csrf') ? json({ csrf_token: 'token' }) : failure('INVALID_CREDENTIALS');
    open();
    const keyboard = await fillLogin();
    await keyboard.click(screen.getByRole('button', { name: '显示密码' }));
    expect((screen.getByLabelText('密码', { exact: true }) as HTMLInputElement).type).toBe('text');
    await keyboard.click(screen.getByRole('button', { name: '登录' }));
    await screen.findByRole('alert');
    expect((screen.getByLabelText('密码', { exact: true }) as HTMLInputElement).value).toBe('');
    expect((screen.getByLabelText('邮箱') as HTMLInputElement).value).toBe(user.email);
    expect(screen.queryByText('REMOTE SECRET')).toBeNull();
    expect(screen.getByText(/22222222-2222/)).toBeTruthy();
  });

  it('等待中阻止重复提交，离开页面取消请求且不接收过期成功', async () => {
    let resolveLogin!: (response: Response) => void;
    respond = path => path.endsWith('/csrf') ? json({ csrf_token: 'token' }) : path.endsWith('/login') ? new Promise(resolve => { resolveLogin = resolve; }) : json(options);
    open();
    const keyboard = await fillLogin();
    const button = screen.getByRole('button', { name: '登录' });
    await keyboard.dblClick(button);
    expect(calls.filter(call => call.path.endsWith('/login'))).toHaveLength(1);
    await keyboard.click(screen.getByRole('link', { name: '使用邀请注册' }));
    expect(calls.find(call => call.path.endsWith('/login'))!.init!.signal!.aborted).toBe(true);
    await act(async () => resolveLogin(json({ user })));
    expect(window.location.pathname).toBe('/register');
  });

  it('限流倒计时期间禁止重试，不自动重发登录', async () => {
    respond = path => path.endsWith('/csrf') ? json({ csrf_token: 'token' }) : failure('RATE_LIMITED', 429, { 'Retry-After': '2' });
    open();
    const keyboard = await fillLogin();
    await keyboard.click(screen.getByRole('button', { name: '登录' }));
    await screen.findByText(/2 秒后可重试/);
    expect((screen.getByRole('button', { name: /秒后可重试/ }) as HTMLButtonElement).disabled).toBe(true);
    await waitFor(() => expect((screen.getByRole('button', { name: '登录' }) as HTMLButtonElement).disabled).toBe(false), { timeout: 3000 });
    expect(calls.filter(call => call.path.endsWith('/login'))).toHaveLength(1);
  });

  it('未知子路由保持未找到，不冒充已实现功能', () => {
    open('/app/not-a-real-page');
    expect(screen.getByRole('heading', { name: '没有找到这一页' })).toBeTruthy();
    expect(calls).toHaveLength(0);
  });

  it.each(['pagehide', 'hidden'])('登录在%s时清空密码并取消POST，恢复不接收旧成功', async event => {
    let resolveLogin!: (response: Response) => void;
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
    respond = path => path.endsWith('/csrf') ? json({ csrf_token: 'token' }) : new Promise(resolve => { resolveLogin = resolve; });
    open();
    const keyboard = await fillLogin();
    await keyboard.click(screen.getByRole('button', { name: '登录' }));
    if (event === 'hidden') { visibility.mockReturnValue('hidden'); fireEvent(document, new Event('visibilitychange')); }
    else fireEvent(window, new Event('pagehide'));
    expect((screen.getByLabelText('密码', { exact: true }) as HTMLInputElement).value).toBe('');
    expect(calls.find(call => call.path.endsWith('/login'))!.init!.signal!.aborted).toBe(true);
    visibility.mockReturnValue('visible');
    fireEvent(window, new Event('pageshow'));
    fireEvent(document, new Event('visibilitychange'));
    await act(async () => resolveLogin(json({ user })));
    expect(window.location.pathname).toBe('/login');
    expect((screen.getByLabelText('邮箱') as HTMLInputElement).value).toBe(user.email);
    expect(calls.filter(call => call.path.endsWith('/login'))).toHaveLength(1);
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('邀请注册', () => {
  it('展示实际政策，明确分别同意后发送当前版本，成功不自动登录', async () => {
    open('/register');
    const keyboard = await fillRegistration();
    expect(screen.getByText('仅用于本机验证账号流程。')).toBeTruthy();
    const checks = screen.getAllByRole('checkbox') as HTMLInputElement[];
    expect(checks.every(check => !check.checked)).toBe(true);
    const submit = screen.getByRole('button', { name: '创建账号' }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    await keyboard.click(checks[0]);
    expect(submit.disabled).toBe(true);
    await keyboard.click(checks[1]);
    await keyboard.click(submit);
    await screen.findByRole('heading', { name: '账号已创建' });
    const posted = JSON.parse(calls.find(call => call.path.endsWith('/register'))!.init!.body as string);
    expect(posted.policy_versions).toEqual(options.registration.policy_versions);
    expect(posted.password).toBe('  Forest-River-482!  ');
    expect(calls.some(call => call.path.endsWith('/login') || call.path.endsWith('/me'))).toBe(false);
    expect(screen.queryByDisplayValue('private-invitation')).toBeNull();
    await keyboard.click(screen.getByRole('button', { name: '前往登录' }));
    expect((screen.getByLabelText('邮箱') as HTMLInputElement).value).toBe(user.email);
    expect(window.location.search).toBe('');
  });

  it('注册选项读取失败关闭提交，可以重试真实读取', async () => {
    respond = () => failure('REQUEST_FAILED', 503);
    open('/register');
    await screen.findByRole('alert');
    expect((screen.getByRole('button', { name: '创建账号' }) as HTMLButtonElement).disabled).toBe(true);
    respond = () => json({ ...options, registration: { ...options.registration, enabled: false } });
    await userEvent.click(screen.getByRole('button', { name: '重新读取注册说明' }));
    await screen.findByText(/当前暂不开放注册/);
    expect((screen.getByRole('button', { name: '创建账号' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('输入或政策失效会刷新说明并重置同意，不自动使用新版本提交', async () => {
    open('/register');
    const keyboard = await fillRegistration();
    for (const check of screen.getAllByRole('checkbox')) await keyboard.click(check);
    respond = path => path.endsWith('/csrf') ? json({ csrf_token: 'token' }) : path.endsWith('/options') ? json(options) : failure('INVALID_INPUT', 400);
    await keyboard.click(screen.getByRole('button', { name: '创建账号' }));
    await waitFor(() => expect(calls.filter(call => call.path.endsWith('/options'))).toHaveLength(2));
    await waitFor(() => expect((screen.getAllByRole('checkbox') as HTMLInputElement[]).every(check => !check.checked)).toBe(true));
    expect((screen.getByLabelText('密码', { exact: true }) as HTMLInputElement).value).toBe('');
    expect(calls.filter(call => call.path.endsWith('/register'))).toHaveLength(1);
  });

  it('按Unicode码点校验昵称和密码，允许80个emoji昵称及12个码点密码', async () => {
    open('/register');
    const keyboard = await fillRegistration();
    const name = screen.getByLabelText('称呼') as HTMLInputElement;
    await keyboard.clear(name);
    await keyboard.type(name, '📚'.repeat(80));
    expect(name.value).toBe('📚'.repeat(80));
    const password = screen.getByLabelText('密码', { exact: true }) as HTMLInputElement;
    fireEvent.change(password, { target: { value: '📚'.repeat(6) } });
    for (const check of screen.getAllByRole('checkbox')) await keyboard.click(check);
    await keyboard.click(screen.getByRole('button', { name: '创建账号' }));
    await screen.findByRole('alert');
    expect(calls.filter(call => call.path.endsWith('/register'))).toHaveLength(0);
    fireEvent.change(password, { target: { value: '📚'.repeat(12) } });
    await keyboard.click(screen.getByRole('button', { name: '创建账号' }));
    await screen.findByRole('heading', { name: '账号已创建' });
    expect(JSON.parse(calls.find(call => call.path.endsWith('/register'))!.init!.body as string).display_name).toBe('📚'.repeat(80));
  });

  it('注册邮箱只交接一次，登录后退出不恢复旧邮箱输入', async () => {
    open('/register');
    const keyboard = await fillRegistration();
    for (const check of screen.getAllByRole('checkbox')) await keyboard.click(check);
    await keyboard.click(screen.getByRole('button', { name: '创建账号' }));
    await keyboard.click(await screen.findByRole('button', { name: '前往登录' }));
    await keyboard.type(screen.getByLabelText('密码', { exact: true }), 'Forest-River-482!');
    await keyboard.click(screen.getByRole('button', { name: '登录' }));
    await screen.findByRole('heading', { name: '你好，林间读者' });
    respond = path => path.endsWith('/csrf') ? json({ csrf_token: 'token' }) : new Response(null, { status: 204 });
    await keyboard.click(screen.getByRole('button', { name: '退出登录' }));
    await screen.findByRole('heading', { name: '欢迎回来' });
    expect((screen.getByLabelText('邮箱') as HTMLInputElement).value).toBe('');
  });

  it.each(['pagehide', 'hidden'])('注册在%s清空敏感字段和同意，取消POST并在恢复后只重取一次政策', async event => {
    let resolveRegistration!: (response: Response) => void;
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
    open('/register');
    const keyboard = await fillRegistration();
    for (const check of screen.getAllByRole('checkbox')) await keyboard.click(check);
    respond = path => path.endsWith('/csrf') ? json({ csrf_token: 'token' }) : path.endsWith('/register')
      ? new Promise(resolve => { resolveRegistration = resolve; }) : json(options);
    await keyboard.click(screen.getByRole('button', { name: '创建账号' }));
    if (event === 'hidden') { visibility.mockReturnValue('hidden'); fireEvent(document, new Event('visibilitychange')); }
    else fireEvent(window, new Event('pagehide'));
    expect((screen.getByLabelText('密码', { exact: true }) as HTMLInputElement).value).toBe('');
    expect((screen.getByLabelText('邀请码') as HTMLInputElement).value).toBe('');
    expect(calls.find(call => call.path.endsWith('/register'))!.init!.signal!.aborted).toBe(true);
    expect((screen.getByRole('button', { name: '创建账号' }) as HTMLButtonElement).disabled).toBe(true);
    const updated = { ...options, registration: { ...options.registration,
      policy_versions: { terms: 'local-test-updated', privacy: 'local-test-updated' },
      policies: options.registration.policies.map(policy => ({ ...policy, version: 'local-test-updated' })) } };
    respond = () => json(updated);
    visibility.mockReturnValue('visible');
    fireEvent(window, new Event('pageshow'));
    fireEvent(document, new Event('visibilitychange'));
    await screen.findAllByText('版本：local-test-updated');
    expect(calls.filter(call => call.path.endsWith('/options'))).toHaveLength(2);
    expect((screen.getAllByRole('checkbox') as HTMLInputElement[]).every(check => !check.checked)).toBe(true);
    await act(async () => resolveRegistration(json({ user }, 201)));
    expect(screen.queryByRole('heading', { name: '账号已创建' })).toBeNull();
    expect(calls.filter(call => call.path.endsWith('/register'))).toHaveLength(1);
  });

  it('注册页隐藏取消正在读取的政策，旧结果不回填，卸载后不再响应恢复事件', async () => {
    let resolveOptions!: (response: Response) => void;
    respond = () => new Promise(resolve => { resolveOptions = resolve; });
    const view = open('/register');
    await waitFor(() => expect(calls.filter(call => call.path.endsWith('/options'))).toHaveLength(1));
    fireEvent(window, new Event('pagehide'));
    expect(calls[0].init!.signal!.aborted).toBe(true);
    await act(async () => resolveOptions(json(options)));
    expect(screen.queryByText('本机测试服务说明')).toBeNull();
    respond = () => json(options);
    fireEvent(window, new Event('pageshow'));
    await screen.findByText('本机测试服务说明');
    expect(calls.filter(call => call.path.endsWith('/options'))).toHaveLength(2);
    view.unmount();
    fireEvent(window, new Event('pagehide'));
    fireEvent(window, new Event('pageshow'));
    expect(calls.filter(call => call.path.endsWith('/options'))).toHaveLength(2);
  });
});

describe('真实账号入口', () => {
  it('匿名账号页重新转到登录', async () => {
    respond = () => failure('AUTH_REQUIRED');
    open('/app');
    await screen.findByRole('heading', { name: '欢迎回来' });
    expect(window.location.pathname).toBe('/login');
  });

  it('退出失败保留实际账号；成功才清除资料并显示登录', async () => {
    open('/app');
    await screen.findByRole('heading', { name: '你好，林间读者' });
    respond = path => path.endsWith('/csrf') ? json({ csrf_token: 'token' }) : failure('REQUEST_FAILED', 503);
    await userEvent.click(screen.getByRole('button', { name: '退出登录' }));
    await screen.findByRole('alert');
    expect(screen.getByText(user.email)).toBeTruthy();
    respond = path => path.endsWith('/csrf') ? json({ csrf_token: 'token' }) : new Response(null, { status: 204 });
    await userEvent.click(screen.getByRole('button', { name: '退出登录' }));
    await screen.findByRole('heading', { name: '欢迎回来' });
    expect(screen.queryByText(user.email)).toBeNull();
  });

  it('pagehide立即遮蔽私有资料，pageshow重新验证不会展示旧账号', async () => {
    open('/app');
    await screen.findByText(user.email);
    fireEvent(window, new Event('pagehide'));
    expect(screen.queryByText(user.email)).toBeNull();
    respond = () => failure('AUTH_REQUIRED');
    fireEvent(window, new Event('pageshow'));
    await screen.findByRole('heading', { name: '欢迎回来' });
    expect(screen.queryByText(user.email)).toBeNull();
  });
});
