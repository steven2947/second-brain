// @vitest-environment jsdom
/** 自编HTTP验证真实聊天入口与交互；不证明模型效果或数据库隔离。 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { ProductApp } from './ProductApp';
import type { components } from './api/generated';

const id = '11111111-1111-4111-8111-111111111111', runId = '22222222-2222-4222-8222-222222222222', jobId = '33333333-3333-4333-8333-333333333333';
const date = '2026-09-08T00:00:00Z';
const original: components['schemas']['Problem'] = { id, release_id: id, title: '真实选择', original_question: '最初的问题', goal: 'analyze', revision: 0, status: 'active', clarification: { rounds: 0, limit: 5, pending_question: null, closed: false }, current_answer_id: null, library_available: true, created_at: date, updated_at: date };
let problem: typeof original;
let messages: components['schemas']['MessagePage']['items'];
let run: components['schemas']['Run'];
let calls: { path: string; init?: RequestInit }[];
let respond: (path: string, init?: RequestInit) => Response | Promise<Response>;
/** value/status/headers为自编HTTP响应。 */
function json(value: unknown, status = 200, headers?: HeadersInit) { return new Response(JSON.stringify(value), { status, headers }); }
/** path/init是浏览器请求；只模拟公开接口的真实形状。 */
function normal(path: string, init?: RequestInit): Response {
  if (path.endsWith('/me')) return json({ user: { id, email: 'test@example.test', display_name: '读者', theme: 'system', timezone: 'Asia/Shanghai', email_verified_at: null, created_at: date } });
  if (path.endsWith('/csrf')) return json({ csrf_token: 'csrf' });
  if (path.endsWith('/cancel')) { run = { ...run, status: 'cancel_requested' }; return json({ ...run, id: jobId, run_id: runId, result_ref: null }, 202); }
  if (path.endsWith('/messages') && init?.method === 'POST' || path.endsWith('/analyze')) {
    const data = JSON.parse(String(init?.body));
    if (!messages.some(message => message.client_message_id === data.client_message_id && data.client_message_id)) {
      problem = { ...problem, revision: problem.revision + 1 };
      messages.push({ id: crypto.randomUUID(), problem_id: id, sequence: messages.length + 1, role: 'user', kind: 'user_text', content: data.content ?? '请直接分析当前问题。', client_message_id: data.client_message_id ?? null, run_id: runId, created_at: date, published_at: date });
    }
    run = { ...run, input_revision: problem.revision };
    return json({ run_id: runId, job_id: jobId, revision: problem.revision }, 202);
  }
  if (path.includes('/messages')) return json({ items: messages, revision: problem.revision, library_available: problem.library_available, next_cursor: null });
  if (path.includes('/runs/')) return json(run);
  if (path.includes('/jobs/')) return json({ ...run, id: jobId, run_id: runId, result_ref: null });
  return json(problem);
}
/** 无参数；打开当前问题详情。 */
function open() { window.history.replaceState(null, '', `/app/problems/${id}`); return render(<ProductApp />); }
beforeEach(() => {
  problem = structuredClone(original); messages = []; calls = [];
  run = { id: runId, problem_id: id, job_id: jobId, status: 'queued', stage: 'accepted', input_revision: 1, outcome: null, stale: false, error_code: null, started_at: null, finished_at: null };
  respond = normal;
  vi.stubGlobal('fetch', vi.fn((path: string, init?: RequestInit) => { calls.push({ path, init }); return Promise.resolve(respond(path, init)); }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

test('真实消息入口保留Unicode原文，Enter与IME不发送，同内容失败重试复用两个编号', async () => {
  open(); const input = await screen.findByLabelText('补充背景或回应追问');
  await waitFor(() => expect((screen.getByRole('button', { name: '直接分析' }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.change(input, { target: { value: '😀'.repeat(20001) } });
  expect((screen.getByRole('button', { name: '发送消息' }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(input, { target: { value: '😀'.repeat(20000) } });
  expect((screen.getByRole('button', { name: '发送消息' }) as HTMLButtonElement).disabled).toBe(false);
  fireEvent.change(input, { target: { value: '  原话\n😀  ' } });
  fireEvent.keyDown(input, { key: 'Enter' }); fireEvent.keyDown(input, { key: 'Enter', isComposing: true });
  expect(calls.some(call => call.init?.method === 'POST')).toBe(false);
  respond = (path, init) => init?.method === 'POST' ? json({}, 502) : normal(path, init);
  await userEvent.click(screen.getByRole('button', { name: '发送消息' })); await screen.findByRole('alert');
  expect((input as HTMLTextAreaElement).value).toBe('  原话\n😀  ');
  respond = normal; await userEvent.click(screen.getByRole('button', { name: '发送消息' }));
  await screen.findByText('排队中');
  const writes = calls.filter(call => call.init?.method === 'POST');
  expect(writes).toHaveLength(2); expect(writes[0].init?.headers).toEqual(writes[1].init?.headers); expect(writes[0].init?.body).toEqual(writes[1].init?.body);
  expect(JSON.parse(String(writes[1].init?.body))).toMatchObject({ content: '  原话\n😀  ', intent: 'supplement', expected_revision: 0 });
  expect((input as HTMLTextAreaElement).value).toBe('');
});
test('202只显示队列；终态读取真实追问且保留新草稿，停止轮询', async () => {
  open(); const input = await screen.findByLabelText('补充背景或回应追问');
  fireEvent.change(input, { target: { value: '背景' } }); await userEvent.click(screen.getByRole('button', { name: '发送消息' })); await screen.findByText('排队中');
  fireEvent.change(input, { target: { value: '尚未发送的新事实' } });
  run = { ...run, status: 'succeeded', outcome: 'question', finished_at: date };
  problem = { ...problem, revision: 2 };
  messages.push({ id: crypto.randomUUID(), problem_id: id, sequence: 2, role: 'assistant', kind: 'clarification', content: '你愿意为这个选择付出什么？', client_message_id: null, run_id: runId, created_at: date, published_at: date });
  await screen.findByText('你愿意为这个选择付出什么？', {}, { timeout: 3500 });
  expect((input as HTMLTextAreaElement).value).toBe('尚未发送的新事实');
  expect(screen.getByText('AI')).toBeTruthy();
  expect(screen.getByText('追问已生成，请在对话记录中查看。')).toBeTruthy();
  expect(screen.queryByText(/这次任务对应旧背景/)).toBeNull();
  const count = calls.filter(call => call.path.includes('/runs/')).length;
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 2200)); });
  expect(calls.filter(call => call.path.includes('/runs/'))).toHaveLength(count);
});
test('409保留草稿，手动读取修订后才允许显式重发', async () => {
  open(); const input = await screen.findByLabelText('补充背景或回应追问');
  fireEvent.change(input, { target: { value: '冲突草稿' } });
  respond = (path, init) => init?.method === 'POST' ? json({ error: { code: 'REVISION_CONFLICT' } }, 409) : normal(path, init);
  await userEvent.click(screen.getByRole('button', { name: '发送消息' })); await screen.findByRole('alert');
  expect((input as HTMLTextAreaElement).value).toBe('冲突草稿');
  expect((screen.getByRole('button', { name: '发送消息' }) as HTMLButtonElement).disabled).toBe(true);
  problem = { ...problem, revision: 4 }; respond = normal;
  await userEvent.click(screen.getByRole('button', { name: '读取最新背景' }));
  await waitFor(() => expect((screen.getByRole('button', { name: '发送消息' }) as HTMLButtonElement).disabled).toBe(false));
  expect((input as HTMLTextAreaElement).value).toBe('冲突草稿');
  await userEvent.click(screen.getByRole('button', { name: '发送消息' })); await screen.findByText('排队中');
  const writes = calls.filter(call => call.init?.method === 'POST');
  expect(writes).toHaveLength(2); expect(JSON.parse(String(writes[1].init?.body)).expected_revision).toBe(4);
  expect(writes[1].init?.body).not.toBe(writes[0].init?.body);
});
test('取消提交真实POST，处理中只显示请求取消并继续读取终态', async () => {
  run = { ...run, status: 'running', stage: 'understanding' };
  open(); await screen.findByLabelText('补充背景或回应追问');
  await userEvent.click(screen.getByRole('button', { name: '直接分析' }));
  await screen.findByText('处理中'); await userEvent.click(screen.getByRole('button', { name: '取消任务' }));
  await screen.findByText('已请求取消，等待任务停止');
  expect(screen.queryByText('任务已取消，消息仍然保留。')).toBeNull();
  expect(calls.filter(call => call.path.endsWith('/cancel') && call.init?.method === 'POST')).toHaveLength(1);
  run = { ...run, status: 'cancelled', finished_at: date };
  await screen.findByText('已取消', {}, { timeout: 3500 });
});
test.each([401, 404])('消息写入遇到%s清空全部私有内容', async status => {
  open(); const input = await screen.findByLabelText('补充背景或回应追问');
  fireEvent.change(input, { target: { value: '私有消息草稿' } });
  respond = (path, init) => init?.method === 'POST' ? json({ error: { code: 'REQUEST_FAILED', message: 'REMOTE SECRET' } }, status) : normal(path, init);
  await userEvent.click(screen.getByRole('button', { name: '发送消息' }));
  if (status === 401) await screen.findByRole('heading', { name: '欢迎回来' }); else await screen.findByText('问题不存在或当前不可访问');
  expect(screen.queryByDisplayValue('私有消息草稿')).toBeNull(); expect(screen.queryByText('最初的问题')).toBeNull(); expect(screen.queryByText('REMOTE SECRET')).toBeNull();
});
test('页面隐藏取消写入和私有树，晚202不会重新挂载或发起轮询', async () => {
  let finish!: (response: Response) => void;
  respond = (path, init) => init?.method === 'POST' ? new Promise(resolve => { finish = resolve; }) : normal(path, init);
  open(); const input = await screen.findByLabelText('补充背景或回应追问');
  fireEvent.change(input, { target: { value: '隐藏前的草稿' } });
  await userEvent.click(screen.getByRole('button', { name: '发送消息' }));
  await waitFor(() => expect(calls.some(call => call.init?.method === 'POST')).toBe(true));
  const write = calls.find(call => call.init?.method === 'POST')!;
  fireEvent(window, new Event('pagehide'));
  expect(write.init?.signal?.aborted).toBe(true); expect(screen.queryByDisplayValue('隐藏前的草稿')).toBeNull();
  await act(async () => finish(json({ run_id: runId, job_id: jobId, revision: 1 }, 202)));
  expect(calls.some(call => call.path.includes('/runs/'))).toBe(false);
  expect(screen.queryByText('消息已保存，任务已接收。')).toBeNull();
});
test.each([['MODEL_UNAVAILABLE', '模型尚未配置，消息已保存'], ['ANALYSIS_UNAVAILABLE', '正式答案服务正在接入，消息已保存']])('直接分析保留显式意图并显示%s实际失败', async (code, text) => {
  run = { ...run, status: 'failed', error_code: code, finished_at: date };
  open(); const input = await screen.findByLabelText('补充背景或回应追问');
  fireEvent.change(input, { target: { value: '  现在就分析\n保留原话  ' } });
  await userEvent.click(screen.getByRole('button', { name: '直接分析' })); await screen.findByText(text);
  const write = calls.find(call => call.init?.method === 'POST')!;
  expect(write.path).toBe(`/api/v1/problems/${id}/messages`);
  expect(JSON.parse(String(write.init?.body))).toMatchObject({ content: '  现在就分析\n保留原话  ', intent: 'analyze_now' });
  expect((input as HTMLTextAreaElement).value).toBe('');
});
test('429遵守Retry-After，倒计时结束前不重发POST', async () => {
  respond = (path, init) => init?.method === 'POST' ? json({ error: { code: 'RATE_LIMITED' } }, 429, { 'Retry-After': '5' }) : normal(path, init);
  open(); const input = await screen.findByLabelText('补充背景或回应追问');
  fireEvent.change(input, { target: { value: '稍后再发' } });
  await userEvent.click(screen.getByRole('button', { name: '发送消息' })); await screen.findByText('5 秒后可重试');
  expect((screen.getByRole('button', { name: '发送消息' }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: '发送消息' }));
  expect(calls.filter(call => call.init?.method === 'POST')).toHaveLength(1); expect((input as HTMLTextAreaElement).value).toBe('稍后再发');
});
test('月额度耗尽提示额度而非请求频率，保留输入且不会自动重发', async () => {
  respond = (path, init) => init?.method === 'POST' ? json({ error: { code: 'QUOTA_EXCEEDED' } }, 429) : normal(path, init);
  open(); const input = await screen.findByLabelText('补充背景或回应追问');
  fireEvent.change(input, { target: { value: '保留到下次的背景' } });
  await userEvent.click(screen.getByRole('button', { name: '发送消息' }));
  await screen.findByText('本月分析额度已用完，请查看账号额度。草稿已保留。');
  expect(screen.queryByText('请求过于频繁，请等待后手动重试。')).toBeNull();
  expect((input as HTMLTextAreaElement).value).toBe('保留到下次的背景');
  expect(calls.filter(call => call.init?.method === 'POST')).toHaveLength(1);
});
test('覆盖不足的实际终态说明未发布答案，不请求虚构答案ID', async () => {
  run = { ...run, status: 'succeeded', outcome: 'coverage_gap', finished_at: date };
  open(); await screen.findByLabelText('补充背景或回应追问');
  await userEvent.click(screen.getByRole('button', { name: '直接分析' }));
  await screen.findByText('当前知识覆盖不足，本次未发布正式答案。请查看对话中的覆盖说明。');
  expect(calls.some(call => call.path.includes('/answers/'))).toBe(false);
});
test('分页未到末页不恢复旧任务，读完才显示真实关联且保持消息不重复', async () => {
  const first: components['schemas']['MessagePage']['items'][number] = { id: jobId, problem_id: id, sequence: 1, role: 'user', kind: 'user_text', content: '第一条', client_message_id: jobId, run_id: runId, created_at: date, published_at: date };
  const second = { ...first, id, sequence: 2, content: '第二条' };
  problem = { ...problem, revision: 1 };
  respond = (path, init) => path.includes('/messages') ? json({ items: path.includes('cursor=') ? [second] : [first], next_cursor: path.includes('cursor=') ? null : 'signed-next', revision: 1, library_available: true }) : normal(path, init);
  open(); await screen.findByText('第一条');
  expect(calls.some(call => call.path.includes('/runs/'))).toBe(false);
  await userEvent.click(screen.getByRole('button', { name: '加载后续消息' })); await screen.findByText('排队中');
  expect(screen.getAllByText('第一条')).toHaveLength(1); expect(screen.getAllByText('第二条')).toHaveLength(1);
  expect(screen.getByText('当前已加载消息关联的任务')).toBeTruthy();
});
test('服务器已保存但响应丢失，后台读取新修订仍复用原提交，202重放只显示一条消息', async () => {
  problem = { ...problem, revision: 1 };
  messages = [{ id: jobId, problem_id: id, sequence: 1, role: 'user', kind: 'user_text', content: '已有背景', client_message_id: jobId, run_id: runId, created_at: date, published_at: date }];
  open(); const input = await screen.findByLabelText('补充背景或回应追问'); await screen.findByText('排队中');
  fireEvent.change(input, { target: { value: '响应丢失的新事实' } });
  respond = (path, init) => { const response = normal(path, init); return init?.method === 'POST' ? json({}, 502) : response; };
  await userEvent.click(screen.getByRole('button', { name: '发送消息' })); await screen.findByRole('alert');
  await screen.findByText('进行中 · 修订 2', {}, { timeout: 3500 });
  respond = normal; await userEvent.click(screen.getByRole('button', { name: '发送消息' }));
  await screen.findByText('消息已保存，任务已接收。');
  await waitFor(() => expect(screen.getAllByText('响应丢失的新事实')).toHaveLength(1));
  const writes = calls.filter(call => call.init?.method === 'POST');
  expect(writes).toHaveLength(2); expect(writes[0].init?.body).toBe(writes[1].init?.body); expect(writes[0].init?.headers).toEqual(writes[1].init?.headers);
  expect(messages.filter(message => message.content === '响应丢失的新事实')).toHaveLength(1);
});
