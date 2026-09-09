/** 问题客户端的实际fetch接缝；不使用此测试证明服务端归属隔离。 */
import { afterEach, expect, test, vi } from 'vitest';
import { createProblem, readProblem, updateProblem } from './problems';

const id = '00000000-0000-4000-8000-000000000001';
const release = '00000000-0000-4000-8000-000000000002';
const sample = { id, title: '我的问题', original_question: '我的问题', goal: 'act', release_id: release,
  revision: 0, status: 'active', clarification: { rounds: 0, limit: 5, pending_question: null, closed: false },
  current_answer_id: null, library_available: true, created_at: '2026-09-08T00:00:00Z', updated_at: '2026-09-08T00:00:00Z' };
afterEach(() => vi.unstubAllGlobals());

test('创建保留原问题并发送同一次提交的幂等键，不自动重发', async () => {
  const fetcher = vi.fn(async (url: string) => new Response(JSON.stringify(url.endsWith('/csrf') ? { csrf_token: 'test-csrf' } : sample), { status: 200 }));
  vi.stubGlobal('fetch', fetcher);
  await createProblem({ question: '  我的问题  ', goal: 'act', release_id: release }, 'same-submission');
  expect(fetcher).toHaveBeenCalledTimes(2);
  const request = fetcher.mock.calls[1] as unknown as [string, RequestInit];
  expect(request[1].headers).toMatchObject({ 'Idempotency-Key': 'same-submission', 'X-CSRFToken': 'test-csrf' });
  expect(JSON.parse(request[1].body as string).question).toBe('  我的问题  ');
});

test('详情拒绝错对象，写失败不换幂等键自动重试', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ ...sample, id: release }), { status: 200 })));
  await expect(readProblem(id)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  const fetcher = vi.fn(async (url: string) => new Response(JSON.stringify(url.endsWith('/csrf') ? { csrf_token: 'token' } : { error: { code: 'REVISION_CONFLICT' } }), { status: url.endsWith('/csrf') ? 200 : 409 }));
  vi.stubGlobal('fetch', fetcher);
  await expect(updateProblem(id, { title: '新标题', expected_revision: 0 })).rejects.toMatchObject({ status: 409 });
  expect(fetcher).toHaveBeenCalledTimes(2);
});
