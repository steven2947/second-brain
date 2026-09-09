/** 运营DTO白名单与同源写请求测试；不替代后端鉴权。 */
import { afterEach, expect, test, vi } from 'vitest';
import { changeAccountStatus, createInvitation, readFeedbackSummary, readOperations, readQuota, saveQuota } from './adminops';

const owner = '00000000-0000-0000-0000-000000000002', other = '00000000-0000-0000-0000-000000000003';
const quota = { owner_id: owner, period: '2026-09-01', limit_runs: 100, reserved_runs: 2, settled_runs: 6, revision: 3 };
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
/** data为自编业务响应；CSRF请求独立返回正常令牌。 */
function reply(data: unknown) { const fetch = vi.fn(async (path: string) => Response.json(path.endsWith('/csrf') ? { csrf_token: 'fixture-csrf' } : data)); vi.stubGlobal('fetch', fetch); return fetch; }

test('额度绑定请求owner，拒绝无效月份、不安全整数与矛盾占用', async () => {
  for (const change of [{ owner_id: other }, { period: '2026-19-01' }, { period: '2026-09-02' }, { limit_runs: Number.MAX_SAFE_INTEGER + 1 }, { limit_runs: 7 }, { revision: -1 }]) { reply({ ...quota, ...change }); await expect(readQuota(owner)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' }); }
  reply({ ...quota, password: 'never-retain' }); expect(await readQuota(owner)).toEqual(quota);
});
test('聚合拒绝未知状态、重复分类和总数不一致，忽略私有多余字段', async () => {
  reply({ period: '2026-09-01', run_counts: [{ status: 'invented', count: 1 }], total_runs: 1 }); await expect(readOperations()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  reply({ period: '2026-09-01', run_counts: [{ status: 'failed', count: 1 }], total_runs: 2 }); await expect(readOperations()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  reply({ category_counts: [{ category: 'helpful', count: 1 }, { category: 'helpful', count: 1 }], total_feedback: 2 }); await expect(readFeedbackSummary()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  reply({ category_counts: [{ category: 'helpful', count: 1, comment: 'never-retain' }], total_feedback: 1, user_email: 'private@example.test' }); expect(await readFeedbackSummary()).toEqual({ category_counts: [{ category: 'helpful', count: 1 }], total_feedback: 1 });
});
test('邀请只投影回执；拒绝错误交付模式，不保存token与路径', async () => {
  reply({ delivery: 'local_capture', delivery_id: other, expires_at: '2026-09-15T00:00:00Z', token: 'never-retain', path: '/private/fixture' }); expect(await createInvitation('reader@example.test', 'invite-one')).toEqual({ delivery: 'local_capture', delivery_id: other, expires_at: '2026-09-15T00:00:00Z' });
  reply({ delivery: 'email_sent', delivery_id: other, expires_at: '2026-09-15T00:00:00Z' }); await expect(createInvitation('reader@example.test', 'invite-two')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
});
test('重要写操作带真实CSRF和幂等key，不接受错账号状态结果', async () => {
  const fetch = reply(quota); await saveQuota(owner, 100, 3, '2026-09-01', 'quota-one'); const request = fetch.mock.calls[1] as unknown as [string, RequestInit]; expect(request[1].method).toBe('PUT'); expect(new Headers(request[1].headers).get('X-CSRFToken')).toBe('fixture-csrf'); expect(new Headers(request[1].headers).get('Idempotency-Key')).toBe('quota-one');
  reply({ id: other, email: 'reader@example.test', display_name: '自编读者', status: 'disabled' }); await expect(changeAccountStatus(owner, 'disabled', 'active', '明确测试', 'status-one')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
});
