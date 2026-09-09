/** 同源传输边界；decoder校验未知响应，options只携带本次请求数据，不持久化。 */
export class ApiFailure extends Error {
  /** code/status为公开错误标识，requestId/retryAfter用于安全排障与等待提示。 */
  constructor(public code: string, public status = 0, public requestId?: string, public retryAfter?: number) {
    super(code);
  }
}
/** value为未知JSON，拒绝数组、null和原始值。 */
export function objectValue(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid object');
  return value as Record<string, unknown>;
}

/** response是失败HTTP响应，payload仅提取受限代码和追踪号，不显示服务端自由文本。 */
function responseFailure(response: Response, payload: unknown): ApiFailure {
  let error: Record<string, unknown> = {};
  try { error = objectValue(objectValue(payload).error); } catch { /* HTML等错误只呈现通用信息。 */ }
  const code = typeof error.code === 'string' && /^[A-Z_]{1,80}$/.test(error.code) ? error.code : 'REQUEST_FAILED';
  const requestId = typeof error.request_id === 'string' && /^[a-f0-9-]{36}$/i.test(error.request_id) ? error.request_id : undefined;
  const retry = response.headers.get('Retry-After');
  const retryAfter = retry && /^\d+$/.test(retry) ? Math.min(Number(retry), 86400) : undefined;
  return new ApiFailure(code, response.status, requestId, retryAfter);
}

/** path/init是内部同源请求，decoder限定响应结构，signal让页面卸载能取消读取。 */
async function fetchOnce<T>(path: string, decoder: (value: unknown) => T, init: RequestInit, signal?: AbortSignal, timeoutMs = 10000): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) controller.abort();
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    controller.signal.throwIfAborted();
    const response = await fetch(path, { ...init, signal: controller.signal, credentials: 'same-origin', cache: 'no-store', redirect: 'error' });
    let payload: unknown;
    try { payload = response.status === 204 ? undefined : await response.json(); }
    catch { if (response.ok) throw new ApiFailure('INVALID_RESPONSE', response.status); }
    if (!response.ok) throw responseFailure(response, payload);
    try { return decoder(payload); } catch { throw new ApiFailure('INVALID_RESPONSE', response.status); }
  } catch (error) {
    if (signal?.aborted) throw new DOMException('请求已取消', 'AbortError');
    if (timedOut) throw new ApiFailure('REQUEST_TIMEOUT');
    if (error instanceof ApiFailure) throw error;
    throw new ApiFailure('NETWORK_ERROR');
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}

/** path只允许/api/v1；decoder为运行时校验，options不落盘且绝不自动重发写操作。 */
export async function requestJson<T>(path: string, decoder: (value: unknown) => T, options: { method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'; body?: unknown; signal?: AbortSignal; timeoutMs?: number; idempotencyKey?: string } = {}): Promise<T> {
  if (!path.startsWith('/api/v1/') || /[\\\r\n]/.test(path)) throw new ApiFailure('INVALID_REQUEST');
  if (options.timeoutMs !== undefined && (!Number.isInteger(options.timeoutMs) || options.timeoutMs < 1 || options.timeoutMs > 60000)) throw new ApiFailure('INVALID_REQUEST');
  const method = options.method ?? 'GET';
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (options.idempotencyKey !== undefined) {
    if (method === 'GET' || !/^[!-~]{1,128}$/.test(options.idempotencyKey)) throw new ApiFailure('INVALID_REQUEST');
    headers['Idempotency-Key'] = options.idempotencyKey;
  }
  if (method !== 'GET') {
    const token = await fetchOnce('/api/v1/auth/csrf', value => {
      const token = objectValue(value).csrf_token;
      if (typeof token !== 'string' || token.length < 1 || token.length > 256 || /[\r\n]/.test(token)) throw new Error('Invalid CSRF');
      return token;
    }, { method: 'GET' }, options.signal);
    headers['X-CSRFToken'] = token;
    headers['Content-Type'] = 'application/json';
  }
  return fetchOnce(path, decoder, { method, headers, ...(method === 'GET' ? {} : { body: JSON.stringify(options.body ?? {}) }) }, options.signal, options.timeoutMs);
}
