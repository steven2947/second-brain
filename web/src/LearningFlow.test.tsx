// @vitest-environment jsdom
/** 自编HTTP夹具验证学习交互；不是对真实模型建议质量的验收。 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { ProductApp } from './ProductApp';
import { readLearning } from './api/learning';
import type { LearningDetail, LearningJob, LearningTurn } from './api/learning';

const id = '00000000-0000-0000-0000-000000000001', exerciseId = '00000000-0000-0000-0000-000000000002', jobId = '00000000-0000-0000-0000-000000000003', date = '2026-09-08T00:00:00Z';
let detail: LearningDetail, calls: { path: string; init: RequestInit }[], handler: (path: string, init: RequestInit) => Response;
/** path/init代表真实前端请求，返回自编知识和持久记录形状，不调用外部模型。 */
function normal(path: string, init: RequestInit): Response {
  if (path.endsWith('/me')) return Response.json({ user: { id, email: 'reader@example.test', display_name: '读者', theme: 'system', timezone: 'Asia/Shanghai', email_verified_at: null, created_at: date } });
  if (path.endsWith('/csrf')) return Response.json({ csrf_token: 'fixture-csrf' });
  if (path === '/api/v1/libraries') return Response.json({ items: [{ id, library_id: id, title: '自编学习库', description: '', content_version: 'a'.repeat(24), book_count: 1, card_count: 1 }], next_cursor: null });
  if (path.includes('/cards')) return Response.json({ release_id: id, content_version: 'a'.repeat(24), items: detail.basis_cards, next_cursor: null });
  if (path === '/api/v1/learning' && init.method === 'POST') { const data = JSON.parse(String(init.body)); detail.session = { ...detail.session, ...data }; return Response.json(detail.session, { status: 201 }); }
  if (path.startsWith('/api/v1/learning?')) return Response.json({ items: [detail.session], next_cursor: null });
  if (path.endsWith('/messages')) { detail.session.revision += 1; return Response.json({ run_id: jobId, job_id: jobId, revision: detail.session.revision }, { status: 202 }); }
  if (path.includes('/jobs/')) return Response.json({ id: jobId, learning_session_id: id, run_id: jobId, status: 'failed', stage: 'accepted', error_code: 'MODEL_UNAVAILABLE', started_at: null, finished_at: date } satisfies LearningJob);
  if (path.endsWith('/archive')) { detail.session.status = 'archived'; detail.session.revision += 1; return Response.json(detail.session); }
  return Response.json(detail);
}
beforeEach(() => {
  detail = { session: { id, release_id: id, problem_id: null, title: '学习反馈原理', goal: '弄清适用边界', basis_card_ids: ['card.A'], revision: 0, status: 'active', created_at: date, updated_at: date }, items: [], next_cursor: null, library_available: true, active_job: null,
    basis_cards: [{ release_id: id, card_id: 'card.A', type: 'method', title: '小步反馈', statement: '先观察实际变化，再决定扩大投入。', book: { id: 'book.A', title: '自编学习手册', author_display: '测试作者甲', metadata_status: 'verified' } }] };
  calls = []; handler = normal;
  vi.stubGlobal('fetch', vi.fn((path: string, init: RequestInit) => { calls.push({ path, init }); return Promise.resolve(handler(path, init)); }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
/** path为学习路由；history无正文、个人回答或凭证。 */
function open(path = `/app/learning/${id}`) { window.history.replaceState(null, '', path); return render(<ProductApp />); }
/** kind/text为自编输出回合，不代表真实生成效果。 */
function output(kind: LearningTurn['kind'], text: string): LearningTurn { return { id: exerciseId, learning_session_id: id, sequence: 1, kind, content: { text, sections: [] }, run_id: jobId, responds_to_turn_id: null, created_at: date }; }

test('创建只保存所选真实卡与目标，不伪造问题或自动调用模型', async () => {
  open('/app/learning/new'); await screen.findByRole('option', { name: '自编学习库 · 1 本书' });
  fireEvent.change(screen.getByLabelText('知识库'), { target: { value: id } });
  await userEvent.click(await screen.findByRole('checkbox')); fireEvent.change(screen.getByLabelText('学习目标'), { target: { value: '如何在现实中判断边界？' } });
  await userEvent.click(screen.getByRole('button', { name: '创建学习，进入学习室' })); await screen.findByText('目标已保存');
  const writes = calls.filter(call => call.init.method === 'POST'); expect(writes).toHaveLength(1);
  expect(JSON.parse(String(writes[0].init.body))).toEqual({ release_id: id, basis_card_ids: ['card.A'], goal: '如何在现实中判断边界？' });
  expect(new Headers(writes[0].init.headers).get('Idempotency-Key')).toBeTruthy(); expect(calls.some(call => call.path.includes('/problems'))).toBe(false);
});
test('原理入口只填写可编辑指令，并保留用户已有草稿', async () => {
  open(); const draft = await screen.findByLabelText('想和 AI 继续聊的内容');
  await userEvent.click(screen.getByRole('button', { name: '深入解释原理' })); expect((draft as HTMLTextAreaElement).value).toContain('来龙去脉');
  fireEvent.change(draft, { target: { value: '我的具体困惑，不能丢失' } }); await userEvent.click(screen.getByRole('button', { name: '出一道应用练习' }));
  expect((draft as HTMLTextAreaElement).value).toBe('我的具体困惑，不能丢失'); expect(calls.filter(call => call.init.method === 'POST')).toHaveLength(0);
  expect((screen.getByRole('option', { name: '提交练习回答' }) as HTMLOptionElement).disabled).toBe(true);
});
test('展示完整原理、实际书名作者和逐段卡片引用', async () => {
  detail.items = [output('explanation', '先分清反馈与因果归因。')]; detail.items[0].content.sections = [{ title: '为什么不能立刻扩大投入', body: '同一信号可能来自环境变化。需要先保留替代解释，再设计可区分假设的观察。', basis_card_ids: ['card.A'] }];
  open(); await screen.findByText('先分清反馈与因果归因。'); expect(screen.getByText('同一信号可能来自环境变化。需要先保留替代解释，再设计可区分假设的观察。')).toBeTruthy();
  expect(screen.getByRole('link', { name: /小步反馈 ·《自编学习手册》· 测试作者甲/ }).getAttribute('href')).toContain('cards/card.A');
});
test('回答练习保存真实输入与练习ID；模型未配置不会冒出假讲评', async () => {
  detail.items = [output('exercise', '你将如何判断这次反馈是否可靠？')]; open(); await screen.findByText('你将如何判断这次反馈是否可靠？');
  await userEvent.click(screen.getByRole('button', { name: '回答这道练习' })); fireEvent.change(screen.getByLabelText('我的练习回答'), { target: { value: '我会先列出环境变化这一替代解释。' } });
  await userEvent.click(screen.getByRole('button', { name: '发送，继续和 AI 学习' }));
  await screen.findByText('模型尚未配置，本次未生成内容。', {}, { timeout: 3000 });
  const sent = JSON.parse(String(calls.find(call => call.path.endsWith('/messages'))!.init.body));
  expect(sent).toMatchObject({ mode: 'respond', content: '我会先列出环境变化这一替代解释。', expected_revision: 0, responds_to_turn_id: exerciseId }); expect(sent.client_message_id).toBeTruthy();
  expect(screen.queryByText('本次回答的反馈 · AI 分析')).toBeNull();
});
test('网络结果未知时同体重试复用幂等键与客户端消息ID', async () => {
  handler = (path, init) => path.endsWith('/messages') ? Response.json({ error: { code: 'UNAVAILABLE' } }, { status: 503 }) : normal(path, init);
  open(); fireEvent.change(await screen.findByLabelText('想和 AI 继续聊的内容'), { target: { value: '为什么这种方法有效？' } });
  const send = screen.getByRole('button', { name: '发送，继续和 AI 学习' }); await userEvent.click(send); await screen.findByRole('alert'); await userEvent.click(send);
  await waitFor(() => expect(calls.filter(call => call.path.endsWith('/messages'))).toHaveLength(2));
  const writes = calls.filter(call => call.path.endsWith('/messages')); expect(writes[0].init.body).toBe(writes[1].init.body); expect(new Headers(writes[0].init.headers).get('Idempotency-Key')).toBe(new Headers(writes[1].init.headers).get('Idempotency-Key'));
});
test('刷新恢复实际运行任务，成功后重读发布内容并采用最新修订', async () => {
  detail.active_job = { id: jobId, learning_session_id: id, run_id: jobId, status: 'running', stage: 'evaluating', error_code: null, started_at: date, finished_at: null };
  handler = (path, init) => {
    if (path.includes('/jobs/')) { detail.items = [output('explanation', '这是服务端已发布的完整讲解。')]; detail.session.revision = 2; detail.active_job = null; return Response.json({ id: jobId, learning_session_id: id, run_id: jobId, status: 'succeeded', stage: 'composing', error_code: null, started_at: date, finished_at: date }); }
    return normal(path, init);
  };
  open(); await screen.findByText('这是服务端已发布的完整讲解。', {}, { timeout: 3000 });
  fireEvent.change(screen.getByLabelText('想和 AI 继续聊的内容'), { target: { value: '再讲讲适用边界。' } }); await userEvent.click(screen.getByRole('button', { name: '发送，继续和 AI 学习' }));
  await waitFor(() => expect(calls.some(call => call.path.endsWith('/messages'))).toBe(true));
  expect(JSON.parse(String(calls.find(call => call.path.endsWith('/messages'))!.init.body)).expected_revision).toBe(2);
});
test('隐藏立即清掉个人回答；恢复重新鉴权，撤权不重挂旧内容', async () => {
  open(); fireEvent.change(await screen.findByLabelText('想和 AI 继续聊的内容'), { target: { value: '尚未保存的私有想法' } }); fireEvent(window, new Event('pagehide'));
  expect(screen.queryByDisplayValue('尚未保存的私有想法')).toBeNull(); handler = (path, init) => path.endsWith('/me') ? Response.json({ error: { code: 'AUTH_REQUIRED' } }, { status: 401 }) : normal(path, init);
  fireEvent(window, new Event('pageshow')); await screen.findByRole('heading', { name: '欢迎回来' }); expect(screen.queryByText('小步反馈')).toBeNull(); expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0);
});
test('阅读解码拒绝串父域、非选用卡和无实际回答引用的讲评', async () => {
  detail.items = [{ ...output('explanation', '测试'), learning_session_id: exerciseId }]; await expect(readLearning(id)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  detail.items = [output('explanation', '测试')]; detail.items[0].content.sections = [{ title: '依据', body: '正文', basis_card_ids: ['card.foreign'] }]; await expect(readLearning(id)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  detail.items = [output('feedback', '你已掌握')]; await expect(readLearning(id)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
});
test('归档保留原学习内容，隐藏发送表单', async () => {
  detail.items = [output('explanation', '保留完整讲解供回看。')]; open(); await screen.findByText('保留完整讲解供回看。'); await userEvent.click(screen.getByRole('button', { name: '归档这次学习' }));
  await screen.findByText('学习记录已归档'); expect(screen.getByText('保留完整讲解供回看。')).toBeTruthy(); expect(screen.queryByRole('button', { name: '发送，继续和 AI 学习' })).toBeNull();
});
