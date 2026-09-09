/** 馆员展示边界；图像先显示，WebGL不参与登录与私有业务。 */
import { Component, lazy, Suspense, useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import type { PointerEvent, ReactNode } from 'react';
import { ArrowClockwiseIcon, ArrowLeftIcon, ArrowRightIcon, HandWavingIcon } from '@phosphor-icons/react';
import { mascotConfig as config } from './config';
import { createMotion, followPointer, greet, resetMotion, rotateBy } from './motion';
import '../../styles/mascot.css';

/** children为可失败的视觉树；onError只降级展示，不影响页面表单。 */
class VisualBoundary extends Component<{ children: ReactNode; onError: () => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { this.props.onError(); }
  render() { return this.state.failed ? null : this.props.children; }
}
/** query为媒体条件；订阅系统偏好变更，不记个人身份数据。 */
function useMedia(query: string) {
  const [value, setValue] = useState(() => window.matchMedia?.(query).matches ?? false);
  useEffect(() => { const media = window.matchMedia?.(query); if (!media) return; const change = () => setValue(media.matches); change(); media.addEventListener('change', change); return () => media.removeEventListener('change', change); }, [query]);
  return value;
}
/** 无参数；不创建试探性WebGL上下文，真正支持情况交给Canvas错误边界。 */
function webglAvailable() { return typeof window.WebGL2RenderingContext !== 'undefined'; }
/** 无参数；省流量或低规格设备默认不自动启用3D，用户仍可明确选择。 */
function lightweightDevice() {
  const device = navigator as Navigator & { deviceMemory?: number; connection?: { saveData?: boolean } };
  return device.connection?.saveData === true || (device.hardwareConcurrency > 0 && device.hardwareConcurrency <= 2) || (device.deviceMemory !== undefined && device.deviceMemory <= 2);
}

/** 无参数；只在显示区跟随指针，密码输入区域没有任何指针监听。 */
export function Mascot() {
  const region = useRef<HTMLDivElement>(null), motion = useRef(createMotion()), wake = useRef<(() => void) | null>(null);
  const pointer = useRef<{ id: number; x: number; y: number; distance: number } | null>(null);
  const reduced = useMedia('(prefers-reduced-motion: reduce)'), compact = useMedia('(max-width: 767px)'), id = useId();
  const [visible, setVisible] = useState(false), [foreground, setForeground] = useState(document.visibilityState !== 'hidden');
  const [enabled, setEnabled] = useState<boolean | null>(null), [ready, setReady] = useState(false), [failed, setFailed] = useState(false), [attempt, setAttempt] = useState(0), [concept, setConcept] = useState(false);
  const [lightweight] = useState(lightweightDevice);
  const supported = webglAvailable(), automatic = !reduced && !compact && !lightweight;
  const active = supported && (enabled ?? automatic) && visible && foreground && !failed;
  const Scene = useMemo(() => lazy(() => import('./MascotScene').then(module => ({ default: module.MascotScene }))), [attempt]);
  const bindWake = useCallback((value: (() => void) | null) => { wake.current = value; }, []);
  const loaded = useCallback(() => setReady(true), []), failedScene = useCallback(() => { setFailed(true); setReady(false); }, []);
  useEffect(() => {
    const element = region.current;
    if (!element) return;
    if (!window.IntersectionObserver) { setVisible(true); return; }
    const observer = new IntersectionObserver(entries => setVisible(entries.some(entry => entry.isIntersecting)), { threshold: 0.05 });
    observer.observe(element); return () => observer.disconnect();
  }, []);
  useEffect(() => {
    /** 无参数；后台卸载WebGL，不保留动画或指针捕获。 */
    const hide = () => { setForeground(false); pointer.current = null; resetMotion(motion.current); };
    /** 无参数；恢复只按当前可见性决定，业务表单由自身边界处理。 */
    const show = () => setForeground(document.visibilityState !== 'hidden');
    const visibility = () => { if (document.visibilityState === 'hidden') hide(); else show(); };
    window.addEventListener('pagehide', hide); window.addEventListener('pageshow', show); document.addEventListener('visibilitychange', visibility);
    return () => { window.removeEventListener('pagehide', hide); window.removeEventListener('pageshow', show); document.removeEventListener('visibilitychange', visibility); };
  }, []);
  useEffect(() => {
    if (!active) { setReady(false); resetMotion(motion.current); return; }
    if (ready) return;
    const timeout = window.setTimeout(failedScene, 20000); return () => window.clearTimeout(timeout);
  }, [active, ready, failedScene]);
  /** action为明确视觉操作，状态留在ref而不导致应用逐帧渲染。 */
  function change(action: 'left' | 'right' | 'reset' | 'greet') {
    if (!active || !ready) return;
    if (action === 'reset') resetMotion(motion.current);
    else if (action === 'greet') greet(motion.current, performance.now());
    else rotateBy(motion.current, action === 'left' ? -config.keyboardStep : config.keyboardStep);
    wake.current?.();
  }
  /** event为人物展示区内指针；不读取表单区域位置。 */
  function move(event: PointerEvent<HTMLDivElement>) {
    if (!active || !ready) return;
    const held = pointer.current;
    if (held && held.id === event.pointerId) {
      const dx = event.clientX - held.x, dy = event.clientY - held.y;
      held.distance += Math.abs(dx) + Math.abs(dy); held.x = event.clientX; held.y = event.clientY;
      rotateBy(motion.current, dx * config.pointerSensitivity, dy * config.pointerSensitivity);
    } else if (!reduced && event.pointerType !== 'touch') {
      const rect = event.currentTarget.getBoundingClientRect();
      followPointer(motion.current, ((event.clientX - rect.left) / Math.max(rect.width, 1) - 0.5) * 2, ((event.clientY - rect.top) / Math.max(rect.height, 1) - 0.5) * 2);
    }
    wake.current?.();
  }
  /** event为当前捕获指针；释放回正，轻触才问候，浏览器滚动取消不触发问候。 */
  function release(event: PointerEvent<HTMLDivElement>, cancelled = false) {
    const held = pointer.current; if (!held || held.id !== event.pointerId) return;
    pointer.current = null;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    resetMotion(motion.current); if (!cancelled && held.distance < 8) greet(motion.current, performance.now()); wake.current?.();
  }
  return <figure className="mascot-figure"><div ref={region} className="mascot-stage" tabIndex={active && ready ? 0 : -1} role="group" aria-label="可交互馆员" aria-describedby={`${id}-help`}
    onPointerDown={event => { if (!active || !ready || event.button !== 0 || pointer.current) return; pointer.current = { id: event.pointerId, x: event.clientX, y: event.clientY, distance: 0 }; event.currentTarget.setPointerCapture?.(event.pointerId); }}
    onPointerMove={move} onPointerUp={event => release(event)} onPointerCancel={event => release(event, true)}
    onPointerLeave={() => { if (!pointer.current) { followPointer(motion.current, 0, 0); wake.current?.(); } }}
    onKeyDown={event => { const action = ({ ArrowLeft: 'left', ArrowRight: 'right', Home: 'reset', Enter: 'greet', ' ': 'greet' } as const)[event.key as 'ArrowLeft']; if (action && active && ready) { event.preventDefault(); change(action); } }}>
    <img className={`mascot-poster ${active && ready ? 'mascot-poster-hidden' : ''}`} src={concept ? config.conceptUrl : config.posterUrl} alt={concept ? '森林绿服饰馆员概念图，静态展示' : '原创3D馆员：圆框眼镜、森林绿开衫，手持打开的书'} width={800} height={1000} fetchPriority="high" draggable={false} onError={() => { if (!concept) setConcept(true); }} />
    {active && <div className="mascot-canvas"><VisualBoundary key={attempt} onError={failedScene}><Suspense fallback={null}><Scene motion={motion} reduced={reduced} lowPower={compact || lightweight} onReady={loaded} onError={failedScene} bindWake={bindWake} /></Suspense></VisualBoundary></div>}
    {active && !ready && <span className="mascot-state" role="status">正在准备3D，登录可直接使用</span>}
  </div><figcaption id={`${id}-help`}>{failed ? '3D暂不可用，已保留静态展示，不影响登录。' : !supported ? '当前设备使用静态展示，不影响登录。' : active && ready ? '拖动看看馆员 · 轻触打个招呼 · 方向键旋转，Home复位' : reduced ? '已尊重减少动态效果设置，可手动查看静态姿态3D。' : compact ? '手机默认轻量展示，可按需打开3D。' : '原创馆员 · 先显示图像，再按需加载3D'}</figcaption>
    <div className="mascot-controls" aria-label="馆员操作">{active && ready ? <><button type="button" title="向左转" aria-label="馆员向左转" onClick={() => change('left')}><ArrowLeftIcon size={18} /></button><button type="button" title="复位" aria-label="馆员复位" onClick={() => change('reset')}><ArrowClockwiseIcon size={18} /></button><button type="button" title="向右转" aria-label="馆员向右转" onClick={() => change('right')}><ArrowRightIcon size={18} /></button><button type="button" onClick={() => change('greet')} disabled={reduced}><HandWavingIcon size={18} />打个招呼</button></> : supported && <button type="button" onClick={() => { setFailed(false); setEnabled(true); setAttempt(value => value + 1); }}>{failed ? '重新尝试3D' : active ? '准备中…' : '查看3D馆员'}</button>}
      {active && <button type="button" onClick={() => setEnabled(false)}>静态展示</button>}
    </div></figure>;
}
