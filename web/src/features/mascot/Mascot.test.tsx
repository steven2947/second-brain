// @vitest-environment jsdom
/** 视觉边界自编替身测试：检查懒加载/失败/隐藏/偏好，不冒充真实GPU渲染。 */
import { useEffect } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { Mascot } from './Mascot';
import type { SceneProps } from './MascotScene';

const model = vi.hoisted(() => ({ mounted: 0, unmounted: 0, fail: false, last: null as SceneProps | null, wake: vi.fn() }));
vi.mock('./MascotScene', () => ({ MascotScene: (props: SceneProps) => {
  useEffect(() => { model.mounted++; model.last = props; props.bindWake(model.wake); if (model.fail) props.onError(); else props.onReady(); return () => { model.unmounted++; props.bindWake(null); }; }, [props.bindWake, props.onReady, props.onError]);
  return <div data-testid="test-model">自编视觉替身</div>;
} }));
let reduced = false, compact = false, visible: ((value: boolean) => void) | null;
beforeEach(() => {
  reduced = false; compact = false; visible = null; model.mounted = 0; model.unmounted = 0; model.fail = false; model.last = null; model.wake.mockClear();
  vi.stubGlobal('WebGL2RenderingContext', function WebGLStub() {});
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: query.includes('reduced') ? reduced : compact, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  vi.stubGlobal('IntersectionObserver', class { constructor(callback: (entries: { isIntersecting: boolean }[]) => void) { visible = value => callback([{ isIntersecting: value }]); } observe() {} disconnect() {} });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
/** 无参数；模拟真实观察器通知展示区进入视口，不靠固定等待假装已加载。 */
async function enter() { await act(async () => visible?.(true)); }

test('离屏不加载模型，进入后显示操作，离开卸载视觉资源', async () => {
  render(<Mascot />); expect(model.mounted).toBe(0); expect(screen.getByRole('img')).toBeTruthy();
  await enter(); await screen.findByRole('button', { name: '馆员复位' });
  await act(async () => visible?.(false)); expect(model.unmounted).toBe(1); expect(screen.queryByTestId('test-model')).toBeNull();
});
test('减少动态默认静态，手动3D仍禁止问候动作', async () => {
  reduced = true; render(<Mascot />); await enter(); expect(model.mounted).toBe(0);
  await userEvent.click(screen.getByRole('button', { name: '查看3D馆员' }));
  const wave = await screen.findByRole('button', { name: '打个招呼' }) as HTMLButtonElement;
  expect(wave.disabled).toBe(true); expect(model.last?.reduced).toBe(true);
});
test('手机不自动请求3D，显式打开后可以退回静态', async () => {
  compact = true; render(<Mascot />); await enter(); expect(model.mounted).toBe(0);
  await userEvent.click(screen.getByRole('button', { name: '查看3D馆员' })); await screen.findByRole('button', { name: '馆员复位' });
  await userEvent.click(screen.getByRole('button', { name: '静态展示' })); expect(screen.queryByTestId('test-model')).toBeNull();
});
test('无WebGL保留图像和说明，不尝试导入渲染', async () => {
  vi.stubGlobal('WebGL2RenderingContext', undefined); render(<Mascot />); await enter();
  expect(model.mounted).toBe(0); expect(screen.getByText('当前设备使用静态展示，不影响登录。')).toBeTruthy();
});
test('模型失败降级图像，可显式重试且不牵连表单', async () => {
  model.fail = true; render(<><input aria-label="独立登录邮箱" defaultValue="reader@example.test" /><Mascot /></>); await enter();
  await screen.findByText('3D暂不可用，已保留静态展示，不影响登录。');
  expect((screen.getByLabelText('独立登录邮箱') as HTMLInputElement).value).toBe('reader@example.test');
  model.fail = false; await userEvent.click(screen.getByRole('button', { name: '重新尝试3D' })); await screen.findByRole('button', { name: '馆员复位' });
});
test('方向键/复位使用真实视觉状态，展示区外指针不改变视线', async () => {
  render(<><input aria-label="独立密码" type="password" /><Mascot /></>); await enter(); await screen.findByRole('button', { name: '馆员复位' });
  const region = screen.getByRole('group', { name: '可交互馆员' });
  fireEvent.keyDown(region, { key: 'ArrowRight' }); expect(model.last!.motion.current.targetYaw).toBeGreaterThan(0);
  fireEvent.keyDown(region, { key: 'Home' }); expect(model.last!.motion.current.targetYaw).toBe(0);
  fireEvent.pointerMove(screen.getByLabelText('独立密码'), { clientX: 999, clientY: 222 }); expect(model.last!.motion.current.targetHeadYaw).toBe(0);
  expect(model.wake).toHaveBeenCalled();
});
test('后台立即卸载，恢复后按需重建，旧canvas不空转', async () => {
  render(<Mascot />); await enter(); await screen.findByRole('button', { name: '馆员复位' });
  fireEvent(window, new Event('pagehide')); expect(screen.queryByTestId('test-model')).toBeNull(); expect(model.unmounted).toBe(1);
  fireEvent(window, new Event('pageshow')); await waitFor(() => expect(model.mounted).toBe(2));
});
test('拖动改变真实目标角度，释放回正，轻触才触发短问候', async () => {
  render(<Mascot />); await enter(); await screen.findByRole('button', { name: '馆员复位' });
  const region = screen.getByRole('group', { name: '可交互馆员' });
  /** type/x/y为实际DOM指针事件；JSDOM用MouseEvent补齐pointer标识。 */
  function pointer(type: string, x: number, y: number) { const event = new MouseEvent(type, { bubbles: true, button: 0, clientX: x, clientY: y }); Object.defineProperty(event, 'pointerId', { value: 1 }); Object.defineProperty(event, 'pointerType', { value: 'mouse' }); fireEvent(region, event); }
  pointer('pointerdown', 10, 10); pointer('pointermove', 180, 40);
  expect(model.last!.motion.current.targetYaw).toBe(0.8); expect(model.last!.motion.current.targetPitch).toBeGreaterThan(0);
  pointer('pointerup', 180, 40); expect(model.last!.motion.current.targetYaw).toBe(0); expect(model.last!.motion.current.greetingAt).toBeNull();
  pointer('pointerdown', 40, 40); pointer('pointerup', 40, 40); expect(model.last!.motion.current.greetingAt).not.toBeNull();
});
test('低规格设备默认不启动GPU，用户主动查看才加载', async () => {
  vi.spyOn(navigator, 'hardwareConcurrency', 'get').mockReturnValue(2); render(<Mascot />); await enter(); expect(model.mounted).toBe(0);
  await userEvent.click(screen.getByRole('button', { name: '查看3D馆员' })); await screen.findByRole('button', { name: '馆员复位' }); expect(model.last?.lowPower).toBe(true);
});
