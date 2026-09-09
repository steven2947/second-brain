/** 自编个人记录响应验证；不以客户端夹具证明数据库隔离。 */
import { afterEach, expect, test, vi } from 'vitest';
import { createAction, readActions, readBookmarks, removeBookmark, saveBookmark } from './personal';

const id = '00000000-0000-0000-0000-000000000001', date = '2026-09-08T00:00:00Z';
const bookmark = { id, release_id: id, core_card_id: 'card.甲', note: '我的笔记', available: true, created_at: date, updated_at: date };
afterEach(() => { vi.unstubAllGlobals(); });
test('收藏响应只保留公开字段，撤权备注不能进入客户端', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ items: [{ ...bookmark, available: false, note: '不应泄漏的摘录' }], next_cursor: null })));
  await expect(readBookmarks()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
});
test('保存收藏绑定版本和卡片且发送CSRF；不接受别的卡片', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(Response.json({ csrf_token: 'test-token' })).mockResolvedValueOnce(Response.json({ ...bookmark, core_card_id: 'wrong' }));
  vi.stubGlobal('fetch', fetch);
  await expect(saveBookmark(id, 'card.甲', '我的笔记')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  expect(fetch.mock.calls[1][1]).toMatchObject({ method: 'PUT', headers: { 'X-CSRFToken': 'test-token' }, body: JSON.stringify({ note: '我的笔记' }) });
});
test('取消收藏只有真实204才视为成功', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json({ csrf_token: 'test-token' })).mockResolvedValueOnce(new Response(null, { status: 204 })));
  await expect(removeBookmark(id, 'card.甲')).resolves.toBeUndefined();
});
test('行动不接受非法枚举或负修订；分页不能重复记录', async () => {
  const action = { id, problem_id: id, answer_id: id, action_index: 0, status: 'fake', observation: '', revision: 0, created_at: date, updated_at: date, step: '试验', completion_criteria: '完成', validation_signal: '信号', stop_condition: '超时' };
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ items: [action], next_cursor: null })));
  await expect(readActions()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
});
test('创建行动仅提交答案与真实索引，不发送前端改写的建议', async () => {
  const action = { id, problem_id: id, answer_id: id, action_index: 2, status: 'planned', observation: '', revision: 0, created_at: date, updated_at: date, step: '试验', completion_criteria: '完成', validation_signal: '信号', stop_condition: '超时' };
  const fetch = vi.fn().mockResolvedValueOnce(Response.json({ csrf_token: 'test-token' })).mockResolvedValueOnce(Response.json(action)); vi.stubGlobal('fetch', fetch);
  expect(await createAction(id, 2)).toEqual(action);
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ answer_id: id, action_index: 2 });
});
