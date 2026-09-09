/** 管理身份使用独立API，只接受当前显式权限；验证码与凭据不落浏览器存储。 */
import { objectValue, requestJson } from './client';
import type { components } from './generated';

export const adminPermissionLabels = { 'accounts.view': '查看账号状态', 'accounts.disable': '禁用普通账号', 'quota.manage': '管理运行额度', 'accounts.invite': '签发邀请', 'knowledge.import': '导入知识版本', 'knowledge.review': '审核权利记录', 'knowledge.publish': '发布知识版本', 'knowledge.revoke': '撤销知识发布', 'grants.manage': '管理知识授权', 'operations.view': '查看任务元数据', 'feedback.review': '查看产品反馈摘要' } as const;
export type AdminPermission = keyof typeof adminPermissionLabels;
export type AdminIdentity = components['schemas']['AdminIdentity'];
export type AdminLogin = components['schemas']['AdminLogin'];
export type AdminReauth = components['schemas']['AdminReauth'];
/** value为未知公开文本，不做隐式对象转换。 */
function text(value: unknown): string { if (typeof value !== 'string') throw new Error('Invalid text'); return value; }
/** value为真实会话时间戳，拒绝不可解析日期。 */
function date(value: unknown): string { const result = text(value); if (!Number.isFinite(Date.parse(result))) throw new Error('Invalid date'); return result; }
/** value为管理身份，不返回设备秘密、恢复码或未声明能力。 */
function identity(value: unknown): AdminIdentity {
  const d = objectValue(value), user = objectValue(d.user), id = text(user.id);
  if (!/^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(id) || !Array.isArray(d.granted_permissions)) throw new Error('Invalid identity');
  const permissions = d.granted_permissions.map(value => { const result = text(value); if (!Object.prototype.hasOwnProperty.call(adminPermissionLabels, result)) throw new Error('Invalid permission'); return result as AdminPermission; });
  if (new Set(permissions).size !== permissions.length) throw new Error('Duplicate permissions');
  const verified_at = date(d.verified_at), fresh_until = date(d.fresh_until), session_expires_at = date(d.session_expires_at);
  if (Date.parse(fresh_until) < Date.parse(verified_at) || Date.parse(session_expires_at) <= Date.parse(verified_at)) throw new Error('Invalid session');
  return { user: { id: id.toLowerCase(), email: text(user.email), display_name: text(user.display_name) }, granted_permissions: permissions, verified_at, fresh_until, session_expires_at };
}
/** signal跟随页面身份边界；不复用普通用户的me结果。 */
export function readAdmin(signal?: AbortSignal) { return requestJson('/api/v1/admin/me', identity, { signal }); }
/** data是一次明确的双因素登录；不自动重试或在URL中携带令牌。 */
export function loginAdmin(data: AdminLogin, signal?: AbortSignal) { return requestJson('/api/v1/admin/auth/login', identity, { method: 'POST', body: data, signal }); }
/** data再次验证当前本人，结果必须仍然是原管理员。 */
export function reauthAdmin(userId: string, data: AdminReauth, signal?: AbortSignal) { return requestJson('/api/v1/admin/auth/reauth', value => { const result = identity(value); if (result.user.id !== userId.toLowerCase()) throw new Error('Wrong identity'); return result; }, { method: 'POST', body: data, signal }); }
/** signal取消当前请求；服务端注销成功后才跳转。 */
export function logoutAdmin(signal?: AbortSignal) { return requestJson('/api/v1/admin/auth/logout', value => { if (value !== undefined) throw new Error('Invalid logout'); }, { method: 'POST', signal }); }
