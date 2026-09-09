/** 自编响应验证答案归属、公开字段和只读传输，不证明真实模型语义。 */
import { afterEach, expect, test, vi } from 'vitest';
import { decodeAnswer, readAnswer } from './answers';
import { answerContext, answerFixture, answerId, runId } from './answers.fixture';
afterEach(() => vi.unstubAllGlobals());
test('完整原理保留，嵌套私有字段被丢弃，未知作者与未授权短引保留null', () => {
  const value = answerFixture();
  expect(decodeAnswer({ ...value, private_key: 'PRIVATE', content: { ...value.content, prompt: 'PRIVATE', witness_cards: [{ ...value.content.witness_cards[0], original_card_ref: 'PRIVATE' }] } }, answerId, answerContext)).toEqual(value);
  value.content.sources[0].excerpt = null; value.content.sources[0].quote_available = false; value.content.witness_cards[0].quote = null; value.content.books[0].author_display = null;
  expect(decodeAnswer(value, answerId, answerContext)).toEqual(value);
});
test('拒绝答案、任务、问题、知识版本及修订错配，不接受坏字段或越权短引', () => {
  for (const key of ['id', 'problem_id', 'run_id', 'release_id'] as const) {
    expect(() => decodeAnswer({ ...answerFixture(), [key]: '99999999-9999-4999-8999-999999999999' }, answerId, answerContext)).toThrow();
  }
  expect(() => decodeAnswer({ ...answerFixture(), input_revision: 2 }, answerId, answerContext)).toThrow();
  const value = answerFixture(); value.content.sources[0].quote_available = false;
  expect(() => decodeAnswer(value, answerId, answerContext)).toThrow();
  expect(() => decodeAnswer({ ...answerFixture(), content: { ...answerFixture().content, witness_cards: 'bad' } }, answerId, answerContext)).toThrow();
});
test('合法短引可来自预览以外的位置，但必须绑定该卡证据与当前权限', () => {
  const value = answerFixture(); value.content.witness_cards[0].quote!.text = '同一证据后段的另一句自编原文。';
  expect(decodeAnswer(value, answerId, answerContext)).toEqual(value);
  value.content.witness_cards[0].quote!.evidence_id = 'wrong-evidence';
  expect(() => decodeAnswer(value, answerId, answerContext)).toThrow();
});
test('实际GET核对返回ID，同源无缓存，不自动重试，非法路径不发请求', async () => {
  const fetcher = vi.fn(async () => Response.json(answerFixture())); vi.stubGlobal('fetch', fetcher);
  const request = new AbortController(); await readAnswer(answerId, answerContext, request.signal);
  expect(fetcher).toHaveBeenCalledWith(`/api/v1/answers/${answerId}`, expect.objectContaining({ method: 'GET', credentials: 'same-origin', cache: 'no-store', redirect: 'error' }));
  await expect(readAnswer(runId, answerContext)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(() => readAnswer('../elsewhere', answerContext)).toThrow();
  expect(fetcher).toHaveBeenCalledTimes(2);
});
