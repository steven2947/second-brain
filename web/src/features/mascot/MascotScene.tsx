/** 独立懒加载WebGL渲染；无连续空转，离屏卸载会释放几何/材质/纹理。 */
import { useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Group, LoadingManager, Mesh, Texture } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { mascotConfig as config } from './config';
import { advanceMotion } from './motion';
import type { MotionState } from './motion';

export interface SceneProps { motion: RefObject<MotionState>; reduced: boolean; lowPower?: boolean; onReady: () => void; onError: () => void; bindWake: (wake: (() => void) | null) => void; }
/** scene为本组件独占模型；使用集合避免共享材质重复销毁。 */
function disposeModel(scene: Group) {
  const geometries = new Set<Mesh['geometry']>(), materials = new Set<Mesh['material'] extends Array<infer T> ? T : import('three').Material>(), textures = new Set<Texture>();
  scene.traverse(object => { if (object instanceof Mesh) { geometries.add(object.geometry); for (const material of Array.isArray(object.material) ? object.material : [object.material]) { materials.add(material); for (const value of Object.values(material)) if (value instanceof Texture) textures.add(value); } } });
  textures.forEach(value => value.dispose()); materials.forEach(value => value.dispose()); geometries.forEach(value => value.dispose());
}
/** model为本次加载的原创场景；props仅处理动画和画布状态，不访问表单。 */
function Rig({ model, motion, reduced, onReady, bindWake }: SceneProps & { model: Group }) {
  const turntable = useRef<Group>(null), ready = useRef(false), invalidate = useThree(state => state.invalidate);
  const joints = useRef<{ head: Group | null; arm: Group | null; page: Group | null; angles: number[][] } | null>(null);
  useEffect(() => {
    const head = model.getObjectByName('Head') as Group | undefined, arm = model.getObjectByName('WaveArm') as Group | undefined, page = model.getObjectByName('BookPage') as Group | undefined;
    joints.current = { head: head ?? null, arm: arm ?? null, page: page ?? null, angles: [head, arm, page].map(node => node ? [node.rotation.x, node.rotation.y, node.rotation.z] : [0, 0, 0]) };
    bindWake(() => invalidate()); invalidate();
    return () => { bindWake(null); joints.current = null; };
  }, [model, bindWake, invalidate]);
  useFrame((_, delta) => {
    const moving = advanceMotion(motion.current, delta, performance.now(), reduced), pose = motion.current, nodes = joints.current;
    if (turntable.current) { turntable.current.rotation.y = pose.yaw; turntable.current.rotation.x = pose.pitch; }
    if (nodes?.head) { nodes.head.rotation.y = nodes.angles[0][1] + pose.headYaw; nodes.head.rotation.x = nodes.angles[0][0] + pose.headPitch; }
    if (nodes?.arm) nodes.arm.rotation.z = nodes.angles[1][2] + pose.wave;
    if (nodes?.page) nodes.page.rotation.y = nodes.angles[2][1] + pose.page;
    if (!ready.current) { ready.current = true; onReady(); }
    if (moving) invalidate();
  });
  return <group ref={turntable}><primitive object={model} dispose={null} /></group>;
}
/** props为明确交互与回调；只加载同源固定GLB，禁止模型引入远端纹理。 */
export function MascotScene(props: SceneProps) {
  const [model, setModel] = useState<Group | null>(null), canvas = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    const request = new AbortController(); let owned: Group | null = null;
    /** 无参数；超预算或资产损坏时回静态图，登录不等待此Promise。 */
    async function load() {
      try {
        const response = await fetch(config.modelUrl, { signal: request.signal, credentials: 'omit', redirect: 'error' });
        if (!response.ok) throw new Error('Model unavailable');
        const bytes = await response.arrayBuffer();
        if (request.signal.aborted) return;
        if (bytes.byteLength > config.maxModelBytes) throw new Error('Model exceeds budget');
        const manager = new LoadingManager(); manager.setURLModifier(url => { if (!url.startsWith('data:')) throw new Error('External model resource'); return url; });
        const result = await new GLTFLoader(manager).parseAsync(bytes, '');
        owned = result.scene;
        if (request.signal.aborted) { disposeModel(owned); owned = null; return; }
        if (!owned.getObjectByName('Librarian')) throw new Error('Model contract');
        owned.traverse(object => { if (object instanceof Mesh) object.castShadow = true; });
        setModel(owned);
      } catch { if (!request.signal.aborted) props.onError(); }
    }
    void load();
    return () => { request.abort(); if (owned) { disposeModel(owned); owned = null; } };
  }, [props.onError]);
  useEffect(() => {
    /** event为设备主动丢失GL上下文；不反复重建耗电重试。 */
    const lost = (event: Event) => { event.preventDefault(); props.onError(); };
    const element = canvas.current; element?.addEventListener('webglcontextlost', lost);
    return () => element?.removeEventListener('webglcontextlost', lost);
  }, [model, props.onError]);
  return <Canvas ref={canvas} frameloop="demand" dpr={props.lowPower ? 1 : config.dpr} shadows={props.lowPower ? false : 'soft'} gl={{ antialias: true, alpha: true, powerPreference: 'low-power' }}
    camera={{ position: config.cameraPosition, fov: config.cameraFov }} onCreated={({ camera, gl }) => { camera.lookAt(...config.cameraLookAt); gl.setClearColor(0x000000, 0); }}
    fallback={<span>此设备无法显示3D，请使用静态展示。</span>}>
    <hemisphereLight args={['#f8f5ea', '#66786b', 2.2]} /><directionalLight position={[3, 6, 5]} intensity={3} color="#fff3df" castShadow={!props.lowPower} shadow-mapSize={[512, 512]} shadow-camera-left={-2} shadow-camera-right={2} shadow-camera-top={4} shadow-camera-bottom={-2} shadow-normalBias={0.025} /><directionalLight position={[-4, 2, 1]} intensity={1.2} color="#d5e8ed" />
    {!props.lowPower && <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.015, 0]} receiveShadow><planeGeometry args={[8, 8]} /><shadowMaterial transparent opacity={0.16} /></mesh>}
    {model && <Rig model={model} {...props} />}
  </Canvas>;
}
