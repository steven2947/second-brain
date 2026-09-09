/** 资料写响应必须属于原账号；安全写操作不能接受假成功正文。 */
import { afterEach, expect, test, vi } from 'vitest';
import { changePassword, logoutAll, saveProfile } from './account-settings';
const id = '11111111-1111-4111-8111-111111111111';
afterEach(() => vi.unstubAllGlobals());
test('资料响应错账号拒绝，不用服务返回值切换身份', async () => {
  vi.stubGlobal('fetch', vi.fn(async (path: string) => Response.json(path.endsWith('/csrf') ? { csrf_token: 'fixture' } : { user: { id: '22222222-2222-4222-8222-222222222222', email: 'fixture@example.test', display_name: '另一个人', theme: 'system', timezone: 'UTC', created_at: '2026-09-08T00:00:00Z', email_verified_at: null } })));
  await expect(saveProfile(id, { display_name: '新称呼' })).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
});
test('改密和全退出仅接受204空正文', async () => {
  vi.stubGlobal('fetch', vi.fn(async (path: string) => Response.json(path.endsWith('/csrf') ? { csrf_token: 'fixture' } : { success: true })));
  await expect(changePassword({ current_password: 'fixture-old', new_password: 'fixture-new' })).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  await expect(logoutAll('fixture-old')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
});
