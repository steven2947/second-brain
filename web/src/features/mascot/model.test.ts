/** 实际交付GLB用真实Three加载器解析；此测试不声称GPU画面已验收。 */
import { readFileSync } from 'node:fs';
import { expect, test } from 'vitest';
import { Box3, Group, LoadingManager, Vector3 } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { mascotConfig } from './config';

test('真实GLB低于3MB、没有外部资源、必需动画节点可读且Y轴朝上', async () => {
  const bytes = readFileSync(new URL('../../../public/models/librarian.glb', import.meta.url));
  expect(bytes.readUInt32LE(0)).toBe(0x46546c67); expect(bytes.readUInt32LE(4)).toBe(2);
  expect(bytes.length).toBeLessThanOrEqual(mascotConfig.maxModelBytes);
  const jsonLength = bytes.readUInt32LE(12), manifest = JSON.parse(bytes.subarray(20, 20 + jsonLength).toString());
  expect((manifest.buffers ?? []).every((buffer: { uri?: string }) => buffer.uri === undefined)).toBe(true);
  expect(manifest.images ?? []).toHaveLength(0);
  const manager = new LoadingManager(); manager.setURLModifier(() => { throw new Error('Unexpected external asset'); });
  const model = await new GLTFLoader(manager).parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer, '');
  for (const name of ['Librarian', 'Head', 'WaveArm', 'BookPage']) expect(model.scene.getObjectByName(name)).toBeTruthy();
  expect(model.scene).toBeInstanceOf(Group);
  const bounds = new Box3().setFromObject(model.scene), size = bounds.getSize(new Vector3());
  expect(Math.abs(bounds.min.y)).toBeLessThan(0.03); expect(size.y).toBeGreaterThan(2.5); expect(size.y).toBeLessThan(3.5);
  expect(size.y).toBeGreaterThan(size.x); expect(size.z).toBeLessThan(2);
});
