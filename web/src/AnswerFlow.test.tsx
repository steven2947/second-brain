// @vitest-environment jsdom
/** 自编HTTP场景验证真实路由里的答案界面，不把夹具当作模型质量证据。 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { ProductApp } from './ProductApp';
import { answerFixture, answerId, problemId, runId, jobId } from './api/answers.fixture';
import type { components } from './api/generated';

let answer: ReturnType<typeof answerFixture>, calls: { path: string; init?: RequestInit }[];
let respond: (path: string, init?: RequestInit) => Response | Promise<Response>;
let messages: components['schemas']['MessagePage']['items'];
const date = '2026-09-08T00:00:00Z';
/** path为实际公开接口，只构造本测试所需响应。 */
function normal(path: string) {
  if (path.endsWith('/me')) return Response.json({ user: { id: problemId, email: 'reader@example.test', display_name: '读者', theme: 'system', timezone: 'Asia/Shanghai', email_verified_at: null, created_at: date } });
  if (path.endsWith('/messages')) return Response.json({ items: messages, revision: 2, library_available: true, next_cursor: null });
  if (path.includes('/runs/')) return Response.json({ id: runId, problem_id: problemId, job_id: jobId, status: 'succeeded', stage: 'composing', input_revision: 1, outcome: 'answer', stale: false, error_code: null, started_at: date, finished_at: date });
  if (path.includes('/jobs/')) return Response.json({ id: jobId, run_id: runId, problem_id: problemId, status: 'succeeded', stage: 'composing', result_ref: answerId, error_code: null, started_at: date, finished_at: date });
  if (path.includes('/answers/')) return Response.json(answer);
  return Response.json({ id: problemId, release_id: problemId, title: '自编选择题', original_question: '是否应该改变？', goal: 'analyze', revision: 2, status: 'active', clarification: { rounds: 0, limit: 5, pending_question: null, closed: true }, current_answer_id: answerId, library_available: true, created_at: date, updated_at: date });
}
/** 无参数；由实际私有问题路由完成身份验证和任务恢复。 */
function open() { window.history.replaceState(null, '', `/app/problems/${problemId}`); return render(<ProductApp />); }
beforeEach(() => {
  answer = answerFixture(); calls = []; respond = normal;
  messages = [{ id: jobId, problem_id: problemId, sequence: 1, role: 'user', kind: 'user_text', content: '请分析我的选择', client_message_id: null, run_id: runId, created_at: date, published_at: date }, { id: answerId, problem_id: problemId, sequence: 2, role: 'assistant', kind: 'answer', content: '答案已完成，请打开阅读。', client_message_id: null, run_id: runId, created_at: date, published_at: date }];
  vi.stubGlobal('fetch', vi.fn((path: string, init?: RequestInit) => { calls.push({ path, init }); return Promise.resolve(respond(path, init)); }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
test('实际任务恢复后呈现建议、作者、完整原理和四席缺口；HTML始终作为文本', async () => {
  answer.content.verdict.conclusion = '<img src=x onerror=alert(1)>'; open();
  const view = await screen.findByRole('article', { name: '已发布答案' });
  expect(within(view).getByText('<img src=x onerror=alert(1)>')).toBeTruthy(); expect(view.querySelector('img,script')).toBeNull(); expect(screen.queryByText('RAW_MARKDOWN')).toBeNull();
  expect(within(view).getByText(answer.content.witness_cards[0].principle)).toBeTruthy();
  expect(within(view).getByText('自编作者甲')).toBeTruthy(); expect(within(view).getByText(/书中转引他人观点/)).toBeTruthy();
  for (const label of ['支持席', '反对席', '替代方案席', '证据审查席']) expect(within(view).getByRole('heading', { name: label })).toBeTruthy();
  expect(within(view).getAllByText('席位缺口 · 尚无充分代表')).toHaveLength(2);
  expect(within(view).getByText('完成标准')).toBeTruthy(); expect(within(view).getByText('停止条件')).toBeTruthy();
  expect(within(view).getByRole('region', { name: '系统综合' })).toBeTruthy();
  expect(view.querySelector('a')?.getAttribute('href')).toBe(`/app/library/${problemId}/cards/${encodeURIComponent('card.自编')}`);
  expect(calls.filter(call => call.path.includes('/answers/'))).toHaveLength(1); expect(calls.some(call => call.init?.method === 'POST')).toBe(false);
});
test('最后的续聊问题完整显示，点击仅追加可编辑草稿且不发起POST', async () => {
  open(); const input = await screen.findByLabelText('补充背景或回应追问'); fireEvent.change(input, { target: { value: '已有草稿' } });
  await userEvent.click(await screen.findByRole('button', { name: '把这个问题带回对话' }));
  expect((input as HTMLTextAreaElement).value).toBe(`已有草稿\n\n${answer.content.next_chat_action.prompt}`);
  expect(screen.getByText(answer.content.next_chat_action.prompt)).toBeTruthy();
  expect(screen.getByText('续聊问题已加入输入框，原有草稿已保留。请编辑核对后再发送。')).toBeTruthy();
  expect(calls.some(call => call.init?.method === 'POST')).toBe(false);
});
test('未授权短引显示权限缺口，检索、候选与采用分开陈述', async () => {
  answer.content.sources[0].excerpt = null; answer.content.sources[0].quote_available = false; answer.content.witness_cards[0].quote = null;
  open(); await screen.findByRole('article', { name: '已发布答案' });
  expect(screen.getByText(/当前没有可显示的原文短引/)).toBeTruthy(); expect(screen.queryByText('先限制成本，再开始尝试。')).toBeNull();
  await userEvent.click(screen.getByText('查看检索覆盖与采用范围'));
  expect(screen.getByText('检索涉及 2 本书；出现候选 1 本书；实际采用 1 张卡片。')).toBeTruthy();
});
test('读取失败可手动重读，始终只有GET，401销毁已加载私有答案与草稿', async () => {
  respond = path => path.includes('/answers/') ? Response.json({}, { status: 502 }) : normal(path);
  open(); const input = await screen.findByLabelText('补充背景或回应追问'); fireEvent.change(input, { target: { value: '私有未发送草稿' } });
  await screen.findByText('暂时无法读取已发布答案，草稿仍然保留。');
  respond = normal; await userEvent.click(screen.getByRole('button', { name: '重新读取答案' })); await screen.findByRole('article', { name: '已发布答案' });
  expect(calls.some(call => call.init?.method === 'POST')).toBe(false);
  respond = path => path.includes('/answers/') ? Response.json({ error: { code: 'AUTH_REQUIRED' } }, { status: 401 }) : normal(path);
  await userEvent.click(screen.getByRole('button', { name: '查看这条消息的答案' }));
  await screen.findByRole('heading', { name: '欢迎回来' });
  expect(screen.queryByRole('article', { name: '已发布答案' })).toBeNull(); expect(screen.queryByDisplayValue('私有未发送草稿')).toBeNull();
});
test('历史消息显式打开自己的任务；页面隐藏取消答案读取，晚响应不能恢复内容', async () => {
  messages = [messages[1]]; let finish!: (value: Response) => void;
  respond = path => path.includes('/answers/') ? new Promise(resolve => { finish = resolve; }) : normal(path);
  open(); await screen.findByRole('button', { name: '查看这条消息的答案' }); expect(calls.some(call => call.path.includes('/runs/'))).toBe(false);
  await userEvent.click(screen.getByRole('button', { name: '查看这条消息的答案' }));
  await waitFor(() => expect(calls.some(call => call.path.includes('/answers/'))).toBe(true));
  expect(screen.getByText('已选择的历史消息关联任务')).toBeTruthy();
  const request = calls.find(call => call.path.includes('/answers/'))!; fireEvent(window, new Event('pagehide')); expect(request.init?.signal?.aborted).toBe(true);
  await act(async () => finish(Response.json(answer))); expect(screen.queryByRole('article', { name: '已发布答案' })).toBeNull();
});
