/** 普通账号找回只传本次明确输入，不暴露邮箱存在性或保存重置令牌。 */
import { objectValue, requestJson } from './client';
import type { components } from './generated';
export type RecoveryOptions = Pick<components['schemas']['AuthOptions'], 'password' | 'password_reset'>;
export type RecoveryDelivery = RecoveryOptions['password_reset']['delivery'];
/** value为公开渠道，只接受已实现的三种状态。 */
function delivery(value: unknown): RecoveryDelivery { if (value !== 'disabled' && value !== 'local_capture' && value !== 'smtp') throw new Error('Invalid delivery'); return value; }
/** value是实际auth-options；本页只选择找回和密码要求，不读取个人资料。 */
export function decodeRecoveryOptions(value: unknown): RecoveryOptions {
  const data = objectValue(value), password = objectValue(data.password), reset = objectValue(data.password_reset);
  const min = password.min_length, max = password.max_length, ttl = reset.token_ttl_seconds, mode = delivery(reset.delivery);
  if (typeof min !== 'number' || typeof max !== 'number' || !Number.isSafeInteger(min) || !Number.isSafeInteger(max) || min < 1 || max < min || max > 4096 || typeof ttl !== 'number' || !Number.isSafeInteger(ttl) || ttl < 1 || ttl > 86400 || typeof reset.available !== 'boolean' || reset.available !== (mode !== 'disabled')) throw new Error('Invalid recovery options');
  return { password: { min_length: min, max_length: max }, password_reset: { available: reset.available, delivery: mode, token_ttl_seconds: ttl } };
}
/** signal绑定页面生命周期，不能从旧页面保留渠道状态。 */
export const readRecoveryOptions = (signal?: AbortSignal) => requestJson('/api/v1/auth/options', decodeRecoveryOptions, { signal });
/** email是明确找回目标；成功仅证明请求受理，不证明账号存在或邮件送达。 */
export function requestPasswordReset(email: string, signal?: AbortSignal) { return requestJson('/api/v1/auth/password-reset/request', value => { const data = objectValue(value), mode = delivery(data.delivery); if (data.status !== 'accepted' || mode === 'disabled') throw new Error('Invalid acceptance'); return { status: 'accepted' as const, delivery: mode }; }, { method: 'POST', body: { email }, signal }); }
/** token/newPassword来自当前邮件页面；不自动重试，不自动登录。 */
export function confirmPasswordReset(token: string, newPassword: string, signal?: AbortSignal) { return requestJson('/api/v1/auth/password-reset/confirm', value => { if (value !== undefined) throw new Error('Invalid reset'); }, { method: 'POST', body: { token, new_password: newPassword }, signal }); }
/** fragment为邮件的一次性片段；只接受一个token，不支持query回退。 */
export function recoveryToken(fragment: string): string { const params = new URLSearchParams(fragment.replace(/^#/, '')); const token = params.get('token'); return params.size === 1 && token !== null && /^[!-~]{1,512}$/.test(token) ? token : ''; }
