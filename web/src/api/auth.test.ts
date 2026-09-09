import { afterEach, describe, expect, it, vi } from 'vitest';
import { decodeOptions, decodeUser, login, logout, readAuthOptions, readMe, register } from './auth';

const user = { id: '513755f0-d2d2-443a-858f-0b064d8f5f31', email: 'reader@example.test', display_name: '读者', theme: 'system', timezone: 'Asia/Shanghai', created_at: '2026-09-08T00:00:00Z', email_verified_at: null };
const options = { registration: { enabled: true, invitation_required: true, policy_versions: { terms: 'test-v1', privacy: 'test-v1' }, policies: ['terms', 'privacy'].map(kind => ({ kind, version: 'test-v1', title: kind, body: '本机测试', test_only: true })) }, password: { min_length: 12, max_length: 128 }, password_reset: { available: false, delivery: 'disabled', token_ttl_seconds: 1800 }, admin_mfa: { available: false } };
describe('认证公开响应边界', () => {
  afterEach(() => vi.unstubAllGlobals());
  it('只投影公开用户字段，不保留额外敏感字段', () => {
    expect(decodeUser({ user: { ...user, password: 'private', is_staff: true } })).toEqual(user);
    expect(() => decodeUser({ user: { ...user, theme: 'unknown' } })).toThrow();
    expect(() => decodeUser({ user: { ...user, id: 123 } })).toThrow();
  });
  it('拒绝可转换为主题字符串的数组或对象', () => {
    expect(() => decodeUser({ user: { ...user, theme: ['light'] } })).toThrow();
  });
  it('昵称长度按服务端Unicode码点计算，不把合法补充平面字符误拒绝', () => {
    expect(decodeUser({ user: { ...user, display_name: '😀'.repeat(80) } }).display_name).toBe('😀'.repeat(80));
    expect(() => decodeUser({ user: { ...user, display_name: '😀'.repeat(81) } })).toThrow();
  });
  it('保留服务端政策、密码限制和能力，拒绝不完整或版本错配政策', () => {
    expect(decodeOptions(options)).toEqual(options);
    expect(() => decodeOptions({ ...options, password: { min_length: 100, max_length: 10 } })).toThrow();
    expect(() => decodeOptions({ ...options, registration: { ...options.registration, policies: [options.registration.policies[0]] } })).toThrow();
    expect(() => decodeOptions({ ...options, registration: { ...options.registration, policy_versions: { terms: 'new', privacy: 'test-v1' } } })).toThrow();
  });
  it('认证适配器绑定真实契约路径，注册不追加登录，退出只接受空响应', async () => {
    const responses = [options, { user }, { csrf_token: 'token' }, { user }, { csrf_token: 'token' }, { user }, { csrf_token: 'token' }];
    const fetcher = vi.fn(async () => responses.length ? new Response(JSON.stringify(responses.shift()), { status: 200 }) : new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetcher);
    await readAuthOptions();
    await readMe();
    await login({ email: user.email, password: ' not-trimmed ' });
    await register({ email: user.email, display_name: '读者', password: ' not-trimmed ', invite_token: 'test-invite', policy_versions: { terms: 'test-v1', privacy: 'test-v1' } });
    await logout();
    expect(fetcher.mock.calls.map(call => (call as unknown[])[0])).toEqual(['/api/v1/auth/options', '/api/v1/me', '/api/v1/auth/csrf', '/api/v1/auth/login', '/api/v1/auth/csrf', '/api/v1/auth/register', '/api/v1/auth/csrf', '/api/v1/auth/logout']);
  });
});
