/** 纯交互状态测试；连续指针变化不得依赖React逐帧渲染。 */
import { expect, test } from 'vitest';
import { createMotion, followPointer, rotateBy, resetMotion, advanceMotion, greet } from './motion';
import { mascotConfig } from './config';

test('指针与旋转限角，复位回中且静止后停止要求渲染', () => {
  const state = createMotion(); followPointer(state, 99, -99); rotateBy(state, 99, 99);
  expect(Math.abs(state.targetYaw)).toBe(mascotConfig.maxYaw); expect(Math.abs(state.targetPitch)).toBe(mascotConfig.maxPitch);
  expect(Math.abs(state.targetHeadYaw)).toBe(mascotConfig.headYaw);
  resetMotion(state);
  for (let i = 0; i < 200; i++) advanceMotion(state, 0.016, i * 16, false);
  expect(advanceMotion(state, 0.016, 4000, false)).toBe(false); expect(state.yaw).toBe(0);
});
test('减少动态时无视线跟随动画，明确旋转即时生效', () => {
  const state = createMotion(); followPointer(state, 1, 1); rotateBy(state, 0.3, 0.1); greet(state, 0);
  advanceMotion(state, 0.016, 300, true);
  expect(state.headYaw).toBe(0); expect(state.wave).toBe(0); expect(state.yaw).toBe(0.3);
});
test('问候与翻页是短动作，结束后能回到静止', () => {
  const state = createMotion(); greet(state, 100);
  expect(advanceMotion(state, 0.016, 450, false)).toBe(true); expect(state.wave).not.toBe(0); expect(state.page).not.toBe(0);
  expect(advanceMotion(state, 0.016, 2500, false)).toBe(false); expect(state.wave).toBe(0); expect(state.page).toBe(0);
});
