/** 消息与任务公开契约测试；自编响应只验证前端边界。 */
import { afterEach, expect, test, vi } from 'vitest';
import { cancelJob, listMessages, readJob, readRun, sendMessage, startAnalysis } from './runs';

const id = '00000000-0000-4000-8000-000000000001', run = '00000000-0000-4000-8000-000000000002', job = '00000000-0000-4000-8000-000000000003';
const date = '2026-09-08T00:00:00Z';
const message = { id: job, problem_id: id, sequence: 1, role: 'user', kind: 'user_text', content: '原话', client_message_id: job, run_id: run, published_at: date, created_at: date };
const page = { items: [message], revision: 1, library_available: true, next_cursor: null };
const task = { id: run, problem_id: id, job_id: job, status: 'queued', stage: 'accepted', input_revision: 1, outcome: null, stale: false, error_code: null, started_at: null, finished_at: null };
/** value为目标接口响应；csrf接口独立提供真实传输令牌。 */
function mock(value: unknown, status = 200) {
  const fetcher = vi.fn(async (path: string, _init?: RequestInit) => new Response(JSON.stringify(path.endsWith('/csrf') ? { csrf_token: 'csrf' } : value), { status: path.endsWith('/csrf') ? 200 : status }));
  vi.stubGlobal('fetch', fetcher); return fetcher;
}
afterEach(() => vi.unstubAllGlobals());

test('发送原样消息携带CSRF与幂等键，失败不自动重发', async () => {
  const fetcher = mock({ run_id: run, job_id: job, revision: 1 }, 202);
  const data = { content: '  背景\n😀  ', intent: 'supplement' as const, expected_revision: 0, client_message_id: job };
  expect(await sendMessage(id, data, 'same-key')).toEqual({ run_id: run, job_id: job, revision: 1 });
  expect(fetcher.mock.calls[1][1]?.headers).toMatchObject({ 'X-CSRFToken': 'csrf', 'Idempotency-Key': 'same-key' });
  expect(JSON.parse(String(fetcher.mock.calls[1][1]?.body))).toEqual(data);
  const failed = mock({ error: { code: 'REVISION_CONFLICT' } }, 409);
  await expect(sendMessage(id, data, 'same-key')).rejects.toMatchObject({ status: 409 });
  expect(failed).toHaveBeenCalledTimes(2);
});
test('直接分析只有显式修订；取消调用真实job路由', async () => {
  const fetcher = mock({ run_id: run, job_id: job, revision: 1 }, 202);
  await startAnalysis(id, { expected_revision: 0 }, 'analyze-key');
  expect(fetcher.mock.calls[1][0]).toBe(`/api/v1/problems/${id}/analyze`);
  expect(JSON.parse(String(fetcher.mock.calls[1][1]?.body))).toEqual({ expected_revision: 0 });
  const cancellation = mock({ ...task, id: job, run_id: run, result_ref: null, status: 'cancel_requested' });
  expect((await cancelJob(job, undefined, { problemId: id, runId: run })).status).toBe('cancel_requested');
  expect(cancellation.mock.calls[1][0]).toBe(`/api/v1/jobs/${job}/cancel`);
});
test('消息白名单拒绝错归属、重复序号、乱序和未知角色', async () => {
  mock({ ...page, secret: '不能带出', items: [{ ...message, secret: '不能带出' }] });
  expect(await listMessages(id)).toEqual(page);
  for (const items of [[{ ...message, problem_id: run }], [message, { ...message, id: run }], [{ ...message, sequence: 2 }, { ...message, id: run }], [{ ...message, role: 'tool' }]]) {
    mock({ ...page, items }); await expect(listMessages(id)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  }
});
test('任务拒绝未知状态阶段与跨问题关联，分页游标安全编码', async () => {
  const fetcher = mock(page); await listMessages(id, 'signed&next');
  expect(fetcher.mock.calls[0][0]).toBe(`/api/v1/problems/${id}/messages?cursor=signed%26next`);
  mock(task); expect(await readRun(run, undefined, id)).toEqual(task);
  for (const value of [{ ...task, id: job }, { ...task, status: 'imaginary' }, { ...task, stage: '90%' }, { ...task, problem_id: job }]) {
    mock(value); await expect(readRun(run, undefined, id)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  }
  mock({ ...task, id: job, run_id: id, result_ref: null });
  await expect(readJob(job, undefined, { problemId: id, runId: run })).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
});
