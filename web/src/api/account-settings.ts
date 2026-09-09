/** 账号设置复用既有公开API；不把邮箱或权限字段扩成可写输入。 */
import type { components } from './generated';
import { decodeUser } from './auth';
import { requestJson } from './client';
/** owner为当前已读账号，input为公开资料；拒绝错误身份响应。 */
export function saveProfile(owner: string, input: components['schemas']['ProfileInput'], signal?: AbortSignal) { return requestJson('/api/v1/me', value => { const user = decodeUser(value); if (user.id !== owner) throw new Error('Wrong identity'); return user; }, { method: 'PATCH', body: input, signal }); }
/** value只允许204空正文，不能把异常JSON当作成功。 */
function noContent(value: unknown) { if (value !== undefined) throw new Error('Invalid response'); }
/** input为当前和新密码，按原始字符发送；服务端保留本会话。 */
export const changePassword = (input: components['schemas']['PasswordInput'], signal?: AbortSignal) => requestJson('/api/v1/me/password', noContent, { method: 'POST', body: input, signal });
/** password为本人再次认证，成功后全部旧会话均失效。 */
export const logoutAll = (password: string, signal?: AbortSignal) => requestJson('/api/v1/auth/logout-all', noContent, { method: 'POST', body: { password }, signal });
