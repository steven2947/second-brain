/** 公开健康协议不接受内部上下文；返回值只包含界面需要的状态。 */
export type Health = 'ok' | 'unavailable';

/** payload为不可信HTTP JSON；验证后只返回白名单标量。 */
export function decodeHealth(payload: unknown): Health {
  if (typeof payload === 'object' && payload !== null && 'status' in payload) {
    if (payload.status === 'ok' || payload.status === 'unavailable') return payload.status;
  }
  throw new Error('健康响应格式不匹配');
}

/** signal由组件持有，用于取消读取；只访问同源只读健康端点。 */
export async function readHealth(signal: AbortSignal): Promise<Health> {
  const response = await fetch('/health/ready', { signal, cache: 'no-store', credentials: 'same-origin' });
  if (!response.ok && response.status !== 503) throw new Error('服务暂时无法连接');
  return decodeHealth(await response.json());
}
