/** 独立可变的视觉状态；只记录当前姿态，不记录或上传用户指针轨迹。 */
import { mascotConfig as config } from './config';

/** 无参数；每个画布持有自己的短生命周期状态。 */
export function createMotion() { return { yaw: 0, pitch: 0, headYaw: 0, headPitch: 0, targetYaw: 0, targetPitch: 0, targetHeadYaw: 0, targetHeadPitch: 0, wave: 0, page: 0, greetingAt: null as number | null }; }
export type MotionState = ReturnType<typeof createMotion>;
/** value为目标角度，limit为双向限角。 */
const clamp = (value: number, limit: number) => Math.max(-limit, Math.min(limit, Number.isFinite(value) ? value : 0));
/** state为当前视觉状态，x/y是展示区内归一化指针位置。 */
export function followPointer(state: MotionState, x: number, y: number) { state.targetHeadYaw = clamp(x, 1) * config.headYaw; state.targetHeadPitch = clamp(y, 1) * config.headPitch; }
/** state为当前视觉状态，yaw/pitch是明确拖动或按键的增量。 */
export function rotateBy(state: MotionState, yaw: number, pitch = 0) { state.targetYaw = clamp(state.targetYaw + yaw, config.maxYaw); state.targetPitch = clamp(state.targetPitch + pitch, config.maxPitch); }
/** state为当前视觉状态；释放拖动、移出或复位不影响任何业务状态。 */
export function resetMotion(state: MotionState) { state.targetYaw = 0; state.targetPitch = 0; state.targetHeadYaw = 0; state.targetHeadPitch = 0; state.greetingAt = null; }
/** state为当前状态，now为本地单调时间；仅一段短问候，无声音。 */
export function greet(state: MotionState, now: number) { state.greetingAt = now; }
/** state为可变姿态，delta秒/now毫秒为帧时间，reduced禁止非必要动画；返回是否仍需下一帧。 */
export function advanceMotion(state: MotionState, delta: number, now: number, reduced: boolean): boolean {
  const amount = reduced ? 1 : 1 - Math.exp(-config.settleSpeed * Math.min(Math.max(delta, 0), 0.05));
  let moving = false;
  for (const [key, target] of [['yaw', 'targetYaw'], ['pitch', 'targetPitch'], ['headYaw', 'targetHeadYaw'], ['headPitch', 'targetHeadPitch']] as const) {
    const desired = reduced && (key === 'headYaw' || key === 'headPitch') ? 0 : state[target];
    const value = state[key] + (desired - state[key]) * amount;
    if (Math.abs(desired - value) < 0.001) state[key] = desired;
    else { state[key] = value; moving = true; }
  }
  const phase = state.greetingAt === null ? 1 : Math.max(0, (now - state.greetingAt) / config.greetingMs);
  if (reduced || phase >= 1) { state.greetingAt = null; state.wave = 0; state.page = 0; }
  else { state.wave = Math.sin(phase * Math.PI) * Math.sin(phase * Math.PI * 5) * 0.28; state.page = Math.sin(phase * Math.PI) * 0.65; moving = true; }
  return moving;
}
