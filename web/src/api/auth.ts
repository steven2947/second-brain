import type { components } from './generated';
import { objectValue, requestJson } from './client';
import { decodeRecoveryOptions } from './recovery';
export type PublicUser = components['schemas']['PublicUser'];
export type AuthOptions = components['schemas']['AuthOptions'];
/** value为未知字段，max限制意外超大响应；允许空昵称。 */
function string(value: unknown, max = 1000): string {
  if (typeof value !== 'string' || Array.from(value).length > max) throw new Error('Invalid string');
  return value;
}
/** value只允许真正的JSON布尔值。 */
function boolean(value: unknown): boolean {
  if (typeof value !== 'boolean') throw new Error('Invalid boolean');
  return value;
}
/** value为尚未验证的服务端JSON，只返回公开字段。 */
export function decodeUser(value: unknown): PublicUser {
  const user = objectValue(objectValue(value).user);
  const id = string(user.id, 36);
  const theme = user.theme;
  if (!/^[a-f0-9-]{36}$/i.test(id) || typeof theme !== 'string' || !['system', 'light', 'dark'].includes(theme)) throw new Error('Invalid user');
  return { id, email: string(user.email, 254), display_name: string(user.display_name, 80),
    theme: theme as PublicUser['theme'], timezone: string(user.timezone, 64),
    created_at: string(user.created_at, 40), email_verified_at: user.email_verified_at === null ? null : string(user.email_verified_at, 40) };
}
/** value为公开认证能力，核对政策覆盖及版本一致性；不猜测服务端默认值。 */
export function decodeOptions(value: unknown): AuthOptions {
  const data = objectValue(value), registration = objectValue(data.registration), password = objectValue(data.password);
  const versions = objectValue(registration.policy_versions);
  const min = password.min_length, max = password.max_length;
  if (typeof min !== 'number' || typeof max !== 'number' || !Number.isInteger(min) || !Number.isInteger(max) || min < 1 || max < min || max > 4096) throw new Error('Invalid password limits');
  const policy_versions = { terms: string(versions.terms, 100), privacy: string(versions.privacy, 100) };
  if (!Array.isArray(registration.policies) || registration.policies.length !== 2) throw new Error('Incomplete policies');
  const policies = registration.policies.map((value): components['schemas']['TestPolicy'] => {
    const policy = objectValue(value), kind = policy.kind;
    if (kind !== 'terms' && kind !== 'privacy') throw new Error('Invalid policy kind');
    const version = string(policy.version, 100);
    if (!version || policy_versions[kind] !== version) throw new Error('Policy version mismatch');
    return { kind, version, title: string(policy.title, 300), body: string(policy.body, 20000), test_only: boolean(policy.test_only) };
  });
  if (new Set(policies.map(policy => policy.kind)).size !== 2) throw new Error('Duplicate policies');
  return { registration: { enabled: boolean(registration.enabled), invitation_required: boolean(registration.invitation_required), policies, policy_versions },
    password: { min_length: min, max_length: max }, password_reset: decodeRecoveryOptions(data).password_reset, admin_mfa: { available: boolean(objectValue(data.admin_mfa).available) } };
}
/** signal绑定当前页面生命周期；返回真正的匿名能力响应。 */
export const readAuthOptions = (signal?: AbortSignal) => requestJson('/api/v1/auth/options', decodeOptions, { signal });
/** signal绑定当前用户读取；会话失效由调用页处理。 */
export const readMe = (signal?: AbortSignal) => requestJson('/api/v1/me', decodeUser, { signal });
/** input来自表单且不持久化，signal用于取消；写入只发送一次。 */
export const login = (input: components['schemas']['LoginInput'], signal?: AbortSignal) => requestJson('/api/v1/auth/login', decodeUser, { method: 'POST', body: input, signal });
/** input携带用户明确接受的实际政策版本，不自动登录。 */
export const register = (input: components['schemas']['RegistrationInput'], signal?: AbortSignal) => requestJson('/api/v1/auth/register', decodeUser, { method: 'POST', body: input, signal });
/** signal绑定退出动作；只接受无正文204响应。 */
export const logout = (signal?: AbortSignal) => requestJson('/api/v1/auth/logout', value => { if (value !== undefined) throw new Error('Invalid logout response'); }, { method: 'POST', signal });
