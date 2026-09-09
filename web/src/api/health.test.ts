/** 健康协议的公开投影测试，不使用模型或真实用户数据。 */
import { describe, expect, it } from 'vitest';

describe('decodeHealth', () => {
  it('只接受明确的健康状态', async () => {
    const module = await import('./health');
    expect(module.decodeHealth({ status: 'ok' })).toBe('ok');
    expect(module.decodeHealth({ status: 'unavailable' })).toBe('unavailable');
  });
  it('错误结构不能伪装服务健康', async () => {
    const module = await import('./health');
    for (const body of [null, {}, 'ok', { status: true }, { status: 'ready' }]) {
      expect(() => module.decodeHealth(body)).toThrow('健康响应格式不匹配');
    }
  });
  it('返回值不携带服务端多余字段', async () => {
    const module = await import('./health');
    expect(module.decodeHealth({ status: 'ok', internal: 'must-not-render' })).toBe('ok');
  });
});
