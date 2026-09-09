/** 自编公开响应检查找回契约；不包含真实密码和邮件令牌。 */
import { afterEach, expect, test, vi } from 'vitest';
import { confirmPasswordReset, decodeRecoveryOptions, recoveryToken, requestPasswordReset } from './recovery';
const options = { password: { min_length: 12, max_length: 256 }, password_reset: { available: true, delivery: 'smtp', token_ttl_seconds: 1800 } };
afterEach(() => vi.unstubAllGlobals());
test('渠道与可用状态必须一致，不采用未知或缺失配置', () => {
  expect(decodeRecoveryOptions({ ...options, smtp_password: 'private' })).toEqual(options);
  for (const changes of [{ available: false }, { delivery: 'console' }, { token_ttl_seconds: 0 }, { token_ttl_seconds: '1800' }]) expect(() => decodeRecoveryOptions({ ...options, password_reset: { ...options.password_reset, ...changes } })).toThrow();
});
test('仅接受单个有界fragment token，拒绝重复/额外字段/空白', () => {
  expect(recoveryToken('#token=fixture.token-123')).toBe('fixture.token-123');
  for (const fragment of ['', '#token=', '#token=a&token=b', '#token=a&redirect=external', '#token=has%20space', '#token=' + 'a'.repeat(513)]) expect(recoveryToken(fragment)).toBe('');
});
test('受理白名单不传播地址或token，禁用渠道不能冒充受理', async () => {
  let response: unknown = { status: 'accepted', delivery: 'local_capture', token: 'secret', email: 'private' };
  vi.stubGlobal('fetch', vi.fn(async (path: string) => Response.json(path.endsWith('/csrf') ? { csrf_token: 'fixture' } : response)));
  expect(await requestPasswordReset('self@example.test')).toEqual({ status: 'accepted', delivery: 'local_capture' });
  response = { status: 'accepted', delivery: 'disabled' }; await expect(requestPasswordReset('self@example.test')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
});
test('确认只在POST body传token和原始密码，不接受伪成功JSON', async () => {
  const fetch = vi.fn(async (path: string) => Response.json(path.endsWith('/csrf') ? { csrf_token: 'fixture' } : { status: 'success' })); vi.stubGlobal('fetch', fetch);
  await expect(confirmPasswordReset('fixture-token', '  original-password  ')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  const [path, init] = fetch.mock.calls[1] as unknown as [string, RequestInit]; expect(path).toBe('/api/v1/auth/password-reset/confirm'); expect(JSON.parse(String(init.body))).toEqual({ token: 'fixture-token', new_password: '  original-password  ' });
});
