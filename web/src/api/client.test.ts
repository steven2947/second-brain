/** 只替换HTTP传输边界，验证真实请求序列和失败处理；真实API另行联调。 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiFailure, requestJson } from './client';

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe('同源私有API传输', () => {
  it('写入前取得CSRF，保留密码空白，不自动重发POST', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(Response.json({ csrf_token: 'test-token' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetcher);
    await requestJson('/api/v1/auth/logout', value => value, { method: 'POST', body: { password: '  private  ' } });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls[0][0]).toBe('/api/v1/auth/csrf');
    const options = fetcher.mock.calls[1][1];
    expect(options.credentials).toBe('same-origin');
    expect(options.cache).toBe('no-store');
    expect(options.redirect).toBe('error');
    expect(options.headers['X-CSRFToken']).toBe('test-token');
    expect(JSON.parse(options.body).password).toBe('  private  ');
  });
  it('只暴露固定错误与安全追踪号，保留Retry-After', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ error: { code: 'RATE_LIMITED', message: '/private/secret', request_id: '72a3b4c5-d6e7-4890-a123-456789abcdef' } }, { status: 429, headers: { 'Retry-After': '17' } })));
    try { await requestJson('/api/v1/me', value => value); expect.fail('必须拒绝'); }
    catch (error) {
      expect(error).toBeInstanceOf(ApiFailure);
      expect(error).toMatchObject({ code: 'RATE_LIMITED', status: 429, retryAfter: 17 });
      expect(String(error)).not.toContain('/private/secret');
    }
  });
  it('未知HTML错误不回显服务器内容', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<pre>private stack</pre>', { status: 500 })));
    await expect(requestJson('/api/v1/me', value => value)).rejects.toMatchObject({ code: 'REQUEST_FAILED', status: 500 });
  });
  it('拒绝跨站路径与无效成功响应', async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({ unexpected: true }));
    vi.stubGlobal('fetch', fetcher);
    await expect(requestJson('https://evil.test', value => value)).rejects.toMatchObject({ code: 'INVALID_REQUEST' });
    expect(fetcher).not.toHaveBeenCalled();
    await expect(requestJson('/api/v1/me', () => { throw new Error('server data'); })).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });
  it('超时中止请求，且不会自动重试', async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn((_path, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))));
    vi.stubGlobal('fetch', fetcher);
    const result = requestJson('/api/v1/me', value => value).then(() => null, error => error);
    await vi.advanceTimersByTimeAsync(10001);
    expect(await result).toMatchObject({ code: 'REQUEST_TIMEOUT' });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it('较长读取期限必须有界，非法期限不发送请求', async () => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    for (const timeoutMs of [0, -1, 60001, Infinity, 1.5]) {
      await expect(requestJson('/api/v1/me', value => value, { timeoutMs })).rejects.toMatchObject({ code: 'INVALID_REQUEST' });
    }
    expect(fetcher).not.toHaveBeenCalled();
  });
});
