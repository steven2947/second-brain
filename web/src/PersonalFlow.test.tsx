// @vitest-environment jsdom
/** 自编HTTP响应下的实际产品路由交互；数据库隔离另由真实PG验证。 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { ProductApp } from './ProductApp';
import { AnswerFeedback, BookmarkControl, SaveActionControl } from './features/personal/PersonalControls';
import type { ActionRecord, Bookmark } from './api/personal';

const id = '00000000-0000-0000-0000-000000000001', date = '2026-09-08T00:00:00Z';
let action: ActionRecord, bookmark: Bookmark, calls: { path: string; init: RequestInit }[];
let handler: (path: string, init: RequestInit) => Response;
/** path/init为实际请求，fixture仅提供自编无模型响应。 */
function normal(path: string, init: RequestInit): Response {
  if (path.endsWith('/me')) return Response.json({ user: { id, email: 'reader@example.test', display_name: '读者', theme: 'system', timezone: 'Asia/Shanghai', email_verified_at: null, created_at: date } });
  if (path.endsWith('/csrf')) return Response.json({ csrf_token: 'fixture-csrf' });
  if (path.startsWith('/api/v1/bookmarks?')) return Response.json({ items: [bookmark], next_cursor: null });
  if (path.includes('/bookmarks/')) {
    if (init.method === 'DELETE') return new Response(null, { status: 204 });
    bookmark = { ...bookmark, ...JSON.parse(String(init.body)) }; return Response.json(bookmark);
  }
  if (path.startsWith('/api/v1/actions?')) return Response.json({ items: [action], next_cursor: null });
  if (path === '/api/v1/actions') return Response.json(action, { status: 201 });
  if (path.includes('/actions/')) { const data = JSON.parse(String(init.body)); action = { ...action, status: data.status, observation: data.observation, revision: action.revision + 1 }; return Response.json(action); }
  if (path.endsWith('/feedback')) return Response.json({ id, ...JSON.parse(String(init.body)), created_at: date }, { status: 201 });
  if (path.endsWith('/messages')) return Response.json({ items: [], next_cursor: null, revision: 2, library_available: true });
  return Response.json({ id, release_id: id, title: '自编问题', original_question: '先做什么实验？', goal: 'act', revision: 2, status: 'active', clarification: { rounds: 0, limit: 5, pending_question: null, closed: true }, current_answer_id: id, library_available: true, created_at: date, updated_at: date });
}
beforeEach(() => {
  action = { id, problem_id: id, answer_id: id, action_index: 0, status: 'planned', observation: '', revision: 0, created_at: date, updated_at: date, step: '开展一次低成本实验', completion_criteria: '访谈两位用户', validation_signal: '用户愿意试用', stop_condition: '超过一天就暂停' };
  bookmark = { id, release_id: id, core_card_id: 'card.甲', note: '我的私有笔记', available: true, created_at: date, updated_at: date }; calls = []; handler = normal;
  vi.stubGlobal('fetch', vi.fn((path: string, init: RequestInit) => { calls.push({ path, init }); return Promise.resolve(handler(path, init)); }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
/** path为产品已有页面，浏览器history只含路径无私有草稿。 */
function open(path: string) { window.history.replaceState(null, '', path); return render(<ProductApp />); }

test('保存真实观察后带回原问题的可编辑草稿，不自动分析或写浏览器存储', async () => {
  open('/app/actions'); await screen.findByText('开展一次低成本实验');
  fireEvent.change(screen.getByLabelText('实际观察'), { target: { value: '两位用户都提出了不同需求' } });
  fireEvent.change(screen.getByLabelText('执行状态'), { target: { value: 'doing' } });
  expect((screen.getByRole('button', { name: '带着反馈继续和 AI 复盘' }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.click(screen.getByRole('button', { name: '保存行动记录' })); await screen.findByText('行动记录已保存');
  expect(JSON.parse(String(calls.find(call => call.init.method === 'PATCH')!.init.body))).toEqual({ status: 'doing', observation: '两位用户都提出了不同需求', expected_revision: 0 });
  await userEvent.click(screen.getByRole('button', { name: '带着反馈继续和 AI 复盘' }));
  const input = await screen.findByLabelText('补充背景或回应追问') as HTMLTextAreaElement;
  expect(input.value).toContain('两位用户都提出了不同需求'); expect(input.value).toContain('不要把我的主观观察直接当作已证实的因果结论');
  expect(window.location.pathname).toBe(`/app/problems/${id}`); expect(calls.filter(call => call.init.method === 'POST')).toHaveLength(0);
  expect(JSON.stringify(window.history.state)).not.toContain('两位用户'); expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0);
});
test('保存冲突保留观察并阻止覆盖与复盘', async () => {
  handler = (path, init) => init.method === 'PATCH' ? Response.json({ error: { code: 'REVISION_CONFLICT' } }, { status: 409 }) : normal(path, init);
  open('/app/actions'); fireEvent.change(await screen.findByLabelText('实际观察'), { target: { value: '未提交的重要观察' } });
  await userEvent.click(screen.getByRole('button', { name: '保存行动记录' })); await screen.findByRole('alert');
  expect((screen.getByLabelText('实际观察') as HTMLTextAreaElement).value).toBe('未提交的重要观察');
  expect((screen.getByRole('button', { name: '保存行动记录' }) as HTMLButtonElement).disabled).toBe(true);
});
test('失权收藏不显示原备注，仍能取消本人收藏', async () => {
  bookmark.available = false; bookmark.note = null;
  open('/app/bookmarks'); await screen.findByText('这张收藏当前不可访问');
  expect(screen.queryByLabelText('我的理解与笔记')).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: '取消这条收藏' }));
  await waitFor(() => expect(calls.some(call => call.init.method === 'DELETE')).toBe(true));
});
test('卡片页收藏不发送空备注覆盖旧笔记；成功前不显示已收藏', async () => {
  render(<MemoryRouter><BookmarkControl release={id} card="card.甲" onFailure={vi.fn()} /></MemoryRouter>);
  expect(screen.queryByText('已收藏')).toBeNull(); await userEvent.click(screen.getByRole('button', { name: '收藏这张知识卡' }));
  await screen.findByText('已收藏'); expect(JSON.parse(String(calls.find(call => call.init.method === 'PUT')!.init.body))).toEqual({});
  expect(bookmark.note).toBe('我的私有笔记');
});
test('加入行动与答案反馈分别显式保存，不重写原建议或启动模型', async () => {
  render(<MemoryRouter><SaveActionControl answer={id} index={0} disabled={false} onFailure={vi.fn()} /><AnswerFeedback answer={id} onFailure={vi.fn()} /></MemoryRouter>);
  await userEvent.click(screen.getByRole('button', { name: '加入我的行动' })); await screen.findByText('已加入行动记录');
  await userEvent.click(screen.getByText('这次分析对你有帮助吗？')); fireEvent.change(screen.getByLabelText('你更想反馈什么'), { target: { value: 'shallow' } });
  fireEvent.change(screen.getByLabelText('具体说明（可选）'), { target: { value: '希望给出更多替代选项' } }); await userEvent.click(screen.getByRole('button', { name: '提交这次反馈' }));
  await screen.findByText('意见已保存，谢谢你帮助我们改进分析质量。');
  expect(JSON.parse(String(calls.find(call => call.path.endsWith('/feedback'))!.init.body))).toEqual({ answer_id: id, category: 'shallow', comment: '希望给出更多替代选项' });
  expect(calls.some(call => call.path.includes('/analyze'))).toBe(false);
});
test('页面隐藏立即卸载私有笔记，恢复后重新检查会话', async () => {
  open('/app/bookmarks'); await screen.findByDisplayValue('我的私有笔记');
  fireEvent(window, new Event('pagehide')); expect(screen.queryByDisplayValue('我的私有笔记')).toBeNull();
  handler = (path, init) => path.endsWith('/me') ? Response.json({ error: { code: 'AUTH_REQUIRED' } }, { status: 401 }) : normal(path, init);
  fireEvent(window, new Event('pageshow')); await screen.findByRole('heading', { name: '欢迎回来' }); expect(screen.queryByDisplayValue('我的私有笔记')).toBeNull();
});
