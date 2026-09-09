// @vitest-environment jsdom
/** 自编HTTP响应验证问题UI流程；不作为真实数据库或模型验收证据。 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProductApp } from './ProductApp';
import type { components } from './api/generated';

const release = '11111111-1111-4111-8111-111111111111', id = '22222222-2222-4222-8222-222222222222';
const user = { id: release, email: 'reader@example.test', display_name: '读者', theme: 'system', timezone: 'Asia/Shanghai', email_verified_at: null, created_at: '2026-09-08T00:00:00Z' };
const libraries = { items: [{ id: release, library_id: release, title: '自编阅读集', description: '', content_version: 'a'.repeat(24), book_count: 3, card_count: 4 }], next_cursor: null };
const original: components['schemas']['Problem'] = { id, release_id: release, title: '一次选择', original_question: '我的原问题', goal: 'analyze', revision: 0, status: 'active', clarification: { rounds: 0, limit: 5, pending_question: null, closed: false }, current_answer_id: null, library_available: true, created_at: '2026-09-08T00:00:00Z', updated_at: '2026-09-08T00:00:00Z' };
let problem: typeof original;
let calls: { path: string; init?: RequestInit }[];
let respond: (path: string, init?: RequestInit) => Response | Promise<Response>;
/** value/status是自编HTTP正文与状态。 */
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
/** status用于模拟拒绝，自由文本必须不回显。 */
const failure = (status: number) => json({ error: { code: status === 409 ? 'REVISION_CONFLICT' : 'REQUEST_FAILED', message: 'REMOTE SECRET', request_id: release } }, status);
/** path是产品真实路由。 */
function open(path = '/app/problems/new') { window.history.replaceState(null, '', path); return render(<ProductApp />); }
/** path/init为真实fetch参数，模拟最小问题生命周期。 */
function normal(path: string, init?: RequestInit): Response {
  if (path.endsWith('/me')) return json({ user });
  if (path.endsWith('/csrf')) return json({ csrf_token: 'test-csrf' });
  if (path.startsWith('/api/v1/libraries')) return json(libraries);
  if (path.includes('/messages')) return json({ items: [], next_cursor: null, revision: problem.revision, library_available: problem.library_available });
  if (init?.method === 'POST') { const data = JSON.parse(String(init.body)); problem = { ...problem, original_question: data.question, goal: data.goal, release_id: data.release_id }; }
  if (init?.method === 'PATCH') { const data = JSON.parse(String(init.body)); problem = { ...problem, ...data, revision: problem.revision + 1 }; }
  if (path.includes('/problems?')) return json({ items: [problem], next_cursor: null });
  return json(problem);
}
beforeEach(() => { problem = structuredClone(original); calls = []; respond = normal; vi.stubGlobal('fetch', vi.fn((path: string, init?: RequestInit) => { calls.push({ path, init }); return Promise.resolve(respond(path, init)); })); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('本人问题草稿流程', () => {
  it('先验证身份，创建原样内容与中文目标映射，真实CSRF和幂等键，进入详情再改名归档和恢复', async () => {
    open(); await screen.findByRole('option', { name: '自编阅读集 · 3 本书' });
    expect(calls[0].path).toBe('/api/v1/me');
    const question = '  我该怎么选择？\n保留原样  ';
    fireEvent.change(screen.getByLabelText('你的问题'), { target: { value: question } });
    await userEvent.selectOptions(screen.getByLabelText('这次想做什么'), 'act');
    await userEvent.click(screen.getByRole('button', { name: '保存问题' }));
    await screen.findByRole('heading', { name: '对话记录' });
    expect(document.querySelector('.problem-original')?.textContent).toBe(question);
    const created = calls.find(call => call.init?.method === 'POST')!;
    expect(JSON.parse(String(created.init?.body))).toEqual({ question, goal: 'act', release_id: release });
    expect(created.init?.headers).toMatchObject({ 'X-CSRFToken': 'test-csrf', 'Idempotency-Key': expect.stringMatching(/^[a-f0-9-]{36}$/) });
    fireEvent.change(screen.getByLabelText('问题名称'), { target: { value: '新名称' } });
    await userEvent.click(screen.getByRole('button', { name: '保存名称' }));
    await screen.findByRole('heading', { name: '新名称' });
    await userEvent.click(screen.getByRole('button', { name: '归档问题' }));
    await screen.findByRole('button', { name: '恢复归档' });
    await userEvent.click(screen.getByRole('button', { name: '恢复归档' }));
    await screen.findByRole('button', { name: '归档问题' });
    await userEvent.click(screen.getByRole('link', { name: '返回我的问题' }));
    await screen.findByRole('link', { name: '新名称' });
    expect(calls.filter(call => call.init?.method === 'PATCH').map(call => JSON.parse(String(call.init?.body)))).toEqual([{ title: '新名称', expected_revision: 0 }, { status: 'archived', expected_revision: 1 }, { status: 'active', expected_revision: 2 }]);
  });
  it('双击只提交一次；网络结果未知保留草稿，同内容重试使用同一个键', async () => {
    let finish!: (value: Response) => void;
    respond = (path, init) => init?.method === 'POST' ? new Promise(resolve => { finish = resolve; }) : normal(path, init);
    open(); await screen.findByRole('option', { name: '自编阅读集 · 3 本书' });
    fireEvent.change(screen.getByLabelText('你的问题'), { target: { value: '保留草稿' } });
    const save = screen.getByRole('button', { name: '保存问题' });
    fireEvent.click(save); fireEvent.click(save);
    await waitFor(() => expect(calls.filter(call => call.init?.method === 'POST')).toHaveLength(1));
    await act(async () => finish(json({}, 502)));
    await screen.findByRole('alert');
    expect((screen.getByLabelText('你的问题') as HTMLTextAreaElement).value).toBe('保留草稿');
    respond = normal; await userEvent.click(screen.getByRole('button', { name: '保存问题' }));
    await screen.findByRole('heading', { name: '对话记录' });
    const writes = calls.filter(call => call.init?.method === 'POST');
    expect(writes).toHaveLength(2); expect(writes[0].init?.headers).toEqual(writes[1].init?.headers);
  });
  it('冲突保留名称草稿，必须手动重读新修订再明确保存', async () => {
    open(`/app/problems/${id}`); await screen.findByText('我的原问题');
    fireEvent.change(screen.getByLabelText('问题名称'), { target: { value: '未提交名称' } });
    respond = (path, init) => init?.method === 'PATCH' ? failure(409) : normal(path, init);
    await userEvent.click(screen.getByRole('button', { name: '保存名称' }));
    await screen.findByText(/其他操作已更新这个问题/);
    expect((screen.getByLabelText('问题名称') as HTMLInputElement).value).toBe('未提交名称');
    problem = { ...problem, title: '服务器名称', revision: 4 }; respond = normal;
    await userEvent.click(screen.getByRole('button', { name: '读取最新版本' }));
    await screen.findByRole('heading', { name: '服务器名称' });
    expect(calls.filter(call => call.init?.method === 'PATCH')).toHaveLength(1);
    expect((screen.getByLabelText('问题名称') as HTMLInputElement).value).toBe('未提交名称');
    await userEvent.click(screen.getByRole('button', { name: '保存名称' }));
    await screen.findByRole('heading', { name: '未提交名称' });
    expect(JSON.parse(String(calls.filter(call => call.init?.method === 'PATCH').at(-1)?.init?.body)).expected_revision).toBe(4);
  });
  it('列表显式搜索与状态切换，游标翻页有界且更改查询重置', async () => {
    respond = (path, init) => path.includes('/problems?') ? json({ items: [problem], next_cursor: path.includes('cursor=') ? null : 'signed-next' }) : normal(path, init);
    open('/app/problems'); await screen.findByRole('link', { name: '一次选择' });
    fireEvent.change(screen.getByLabelText('搜索我的问题'), { target: { value: '选择' } });
    await userEvent.click(screen.getByRole('button', { name: '搜索' })); await screen.findByRole('link', { name: '一次选择' });
    expect(calls.at(-1)?.path).toContain('q=%E9%80%89%E6%8B%A9');
    await userEvent.click(screen.getByRole('button', { name: '下一页' })); await screen.findByRole('link', { name: '一次选择' });
    expect(calls.at(-1)?.path).toContain('cursor=signed-next');
    await userEvent.click(screen.getByRole('button', { name: '已归档' })); await screen.findByRole('link', { name: '一次选择' });
    expect(calls.at(-1)?.path).toContain('status=archived'); expect(calls.at(-1)?.path).not.toContain('cursor=');
  });
  it('没有获准知识集不能绑定保存，保留明确返回书房入口', async () => {
    respond = (path, init) => path.includes('/libraries') ? json({ items: [], next_cursor: null }) : normal(path, init);
    open(); await screen.findByText(/当前没有获准的知识集/);
    expect(screen.getByRole('link', { name: '返回书房' }).getAttribute('href')).toBe('/app/library');
    expect(screen.queryByRole('button', { name: '保存问题' })).toBeNull();
    expect(calls.some(call => call.init?.method === 'POST')).toBe(false);
  });
  it('不可用知识仍展示本人原文，不伪造澄清、模型或答案', async () => {
    problem = { ...problem, library_available: false, clarification: { ...problem.clarification, pending_question: '不可用知识的旧追问' } };
    open(`/app/problems/${id}`); await screen.findByText('我的原问题');
    expect(screen.getByText(/绑定的知识集当前不可用/)).toBeTruthy();
    expect(screen.queryByText('不可用知识的旧追问')).toBeNull();
    expect(screen.queryByRole('button', { name: /发送|分析/ })).toBeNull();
    expect(screen.queryByRole('progressbar')).toBeNull();
  });
  it.each([401, 404])('写入遇到%s清空所有本人文字，不回显自由错误', async status => {
    open(`/app/problems/${id}`); await screen.findByText('我的原问题');
    fireEvent.change(screen.getByLabelText('问题名称'), { target: { value: '私有名称草稿' } });
    respond = () => failure(status);
    await userEvent.click(screen.getByRole('button', { name: '保存名称' }));
    if (status === 401) await screen.findByRole('heading', { name: '欢迎回来' }); else await screen.findByText('问题不存在或当前不可访问');
    expect(screen.queryByText('我的原问题')).toBeNull(); expect(screen.queryByDisplayValue('私有名称草稿')).toBeNull(); expect(screen.queryByText('REMOTE SECRET')).toBeNull();
  });
  it('隐藏同步清空草稿，晚创建响应不能导航，恢复先重新验证账号', async () => {
    let finish!: (value: Response) => void;
    respond = (path, init) => init?.method === 'POST' ? new Promise(resolve => { finish = resolve; }) : normal(path, init);
    open(); await screen.findByRole('option', { name: '自编阅读集 · 3 本书' });
    fireEvent.change(screen.getByLabelText('你的问题'), { target: { value: '账号一的私有草稿' } });
    await userEvent.click(screen.getByRole('button', { name: '保存问题' }));
    await waitFor(() => expect(calls.some(call => call.init?.method === 'POST')).toBe(true));
    const request = calls.at(-1)!; fireEvent(window, new Event('pagehide'));
    expect(screen.queryByDisplayValue('账号一的私有草稿')).toBeNull(); expect(request.init?.signal?.aborted).toBe(true);
    await act(async () => finish(json(problem))); expect(window.location.pathname).toBe('/app/problems/new');
    respond = (path, init) => path.endsWith('/me') ? json({ user: { ...user, id } }) : normal(path, init);
    const count = calls.length; fireEvent(window, new Event('pageshow'));
    await screen.findByLabelText('你的问题'); expect(calls[count].path).toBe('/api/v1/me');
    expect((screen.getByLabelText('你的问题') as HTMLTextAreaElement).value).toBe('');
    expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0);
  });
  it('换页取消详情读取，晚到的原文不进入新建表单', async () => {
    let finish!: (value: Response) => void;
    respond = (path, init) => path.endsWith(`/problems/${id}`) ? new Promise(resolve => { finish = resolve; }) : normal(path, init);
    open(`/app/problems/${id}`);
    await waitFor(() => expect(calls.some(call => call.path.endsWith(`/problems/${id}`))).toBe(true));
    const request = calls.at(-1)!;
    await userEvent.click(screen.getByRole('link', { name: '返回我的问题' }));
    await screen.findByRole('link', { name: '一次选择' });
    await userEvent.click(screen.getByRole('link', { name: '新建问题' }));
    await screen.findByLabelText('你的问题');
    expect(request.init?.signal?.aborted).toBe(true);
    await act(async () => finish(json({ ...problem, original_question: '不应回填的私有原文' })));
    expect(screen.queryByText('不应回填的私有原文')).toBeNull();
  });
  it('未知问题状态不伪装成有效档案，也不泄漏原文', async () => {
    respond = (path, init) => path.endsWith(`/problems/${id}`) ? json({ ...problem, status: 'unknown' }) : normal(path, init);
    open(`/app/problems/${id}`); await screen.findByText('暂时无法读取，请稍后重试');
    expect(screen.queryByText('我的原问题')).toBeNull(); expect(screen.queryByText('一次选择')).toBeNull();
  });
  it('字符限制按Unicode计数，Enter只换行，编辑内容后的新提交使用新键', async () => {
    respond = (path, init) => init?.method === 'POST' ? failure(400) : normal(path, init);
    open(); await screen.findByLabelText('你的问题');
    const input = screen.getByLabelText('你的问题');
    fireEvent.change(input, { target: { value: '问'.repeat(4001) } });
    expect((screen.getByRole('button', { name: '保存问题' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(input, { target: { value: '😀'.repeat(4000) } });
    expect((screen.getByRole('button', { name: '保存问题' }) as HTMLButtonElement).disabled).toBe(false);
    fireEvent.keyDown(input, { key: 'Enter', isComposing: true });
    expect(calls.some(call => call.init?.method === 'POST')).toBe(false);
    await userEvent.click(screen.getByRole('button', { name: '保存问题' })); await screen.findByRole('alert');
    fireEvent.change(input, { target: { value: '改过的内容' } });
    await userEvent.click(screen.getByRole('button', { name: '保存问题' })); await screen.findByRole('alert');
    const writes = calls.filter(call => call.init?.method === 'POST');
    expect(writes).toHaveLength(2); expect(new Headers(writes[0].init?.headers).get('Idempotency-Key')).not.toBe(new Headers(writes[1].init?.headers).get('Idempotency-Key'));
  });
});
