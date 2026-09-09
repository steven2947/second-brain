/** WP-02本机连通性界面，不冒充已经完成的公共首页或登录系统。 */
import { useEffect, useState } from 'react';
import { BooksIcon, ArrowClockwiseIcon, CheckCircleIcon, WarningCircleIcon } from '@phosphor-icons/react';
import { readHealth } from './api/health';
import type { Health } from './api/health';

/** 展示真实服务状态；refresh改变时取消旧查询，卸载不保留连接或私有缓存。 */
export function App() {
  const [health, setHealth] = useState<Health | 'loading'>('loading');
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timer = setTimeout(() => controller.abort(), 5000);
    setHealth('loading');
    readHealth(controller.signal).then(value => { if (active) setHealth(value); })
      .catch(() => { if (active) setHealth('unavailable'); })
      .finally(() => clearTimeout(timer));
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [refresh]);
  return (
    <main className="bootstrap-shell">
      <header className="brand"><BooksIcon size={30} weight="regular" aria-hidden="true" /><span>第二大脑</span></header>
      <section className="bootstrap-panel" aria-labelledby="bootstrap-heading">
        <p className="development-label">本机工程联调</p>
        <h1 id="bootstrap-heading">知识工作台，<br />从真实连接开始。</h1>
        <p className="description">这里是施工中的连通性检查页。正式首页、可交互馆员、账号与知识分析正在逐步接入。</p>
        <div className="health-panel" role="status" aria-live="polite">
          {health === 'ok' ? <CheckCircleIcon size={26} aria-hidden="true" /> : <WarningCircleIcon size={26} aria-hidden="true" />}
          <div>
            <strong>{health === 'loading' ? '正在检查连接' : health === 'ok' ? '前端、服务端与数据库已连通' : '服务暂时无法连接'}</strong>
            <p>{health === 'ok' ? '只读健康检查通过，尚不代表登录或 AI 功能已完成。' : '可重新检查；没有生成或提交任何分析任务。'}</p>
          </div>
        </div>
        <button type="button" disabled={health === 'loading'} onClick={() => setRefresh(value => value + 1)}>
          <ArrowClockwiseIcon size={18} aria-hidden="true" />重新检查
        </button>
      </section>
      <footer>开发数据与原始书库隔离。此页不提供模型调用。</footer>
    </main>
  );
}
