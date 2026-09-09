/** 馆员唯一外观/交互配置；模型与poster为同源公共资产，无账户或聊天数据。 */
export const mascotConfig = {
  modelUrl: '/models/librarian.glb',
  posterUrl: '/images/librarian-poster-v1.png',
  conceptUrl: '/images/librarian-concept-v1.png',
  maxModelBytes: 3 * 1024 * 1024,
  maxYaw: 0.8, maxPitch: 0.2, headYaw: 0.18, headPitch: 0.1,
  keyboardStep: 0.18, pointerSensitivity: 0.006,
  greetingMs: 1500, settleSpeed: 10,
  dpr: [1, 1.5] as [number, number],
  cameraPosition: [0, 1.65, 6.8] as [number, number, number],
  cameraLookAt: [0, 1.48, 0] as [number, number, number],
  cameraFov: 32,
};
