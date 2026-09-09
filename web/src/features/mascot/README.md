# 馆员组件修改指南

本组件只做视觉交互，不读账号、问题、书库、提示词或密钥。入口为 `Mascot.tsx`，由登录/注册共用的 `AuthShell` 挂载。

## 想改什么，改哪里

| 修改 | 文件/参数 | 验证 |
| --- | --- | --- |
| 换模型与静态图 | `config.ts` 的 modelUrl/posterUrl | 重新运行 model.test；保持命名节点与Y-up契约 |
| 改人物造型、衣服颜色 | `assets/character/build_librarian.py`，或编辑 `.blend` | 重建GLB与真实海报，检查尺寸与穿插 |
| 改旋转幅度、响应速度 | config 的 maxYaw/maxPitch/settleSpeed | motion.test及真实鼠标/触屏 |
| 改构图 | config 的 cameraPosition/cameraLookAt/cameraFov | 桌面和390宽度，头脚不能被裁切 |
| 改材质观感/照明 | `MascotScene.tsx` 的光源 | 与海报区分，必须看真实WebGL效果 |
| 改展示区和按钮样式 | `styles/mascot.css` | 保留44px触摸目标、焦点和固定高度 |

项目根目录执行：

```sh
npm --prefix web run test -- --run src/features/mascot
npm --prefix web run typecheck
npm --prefix web run build
```

模型源与重建命令详见 [原创资产说明](../../../../assets/character/README.md)。网页只发布 `public/models` 与 `public/images`，不能把 `.blend`、`.runtime/model-tools` 或建模工具加进 public。

## 交互和资源生命周期

- 桌面展示区进入视口才导入独立渲染包；静态poster先可见，3D第一帧就绪再替换，不阻塞登录。
- 手机、减少动态、低CPU/内存或省流量模式默认静态；用户可以手动选择3D。减少动态时允许即时旋转，但关闭自动视线与问候；低规格模式DPR=1且无实时阴影。
- 鼠标跟随仅绑定人物区域；拖动限俯仰、释放回中，轻触/问候按钮播放短动作。方向键左右转、Home复位、Enter/Space问候；动作不自动提交任何表单。
- 连续姿态在ref里更新，不逐帧重渲染业务React树。Fiber `frameloop="demand"` 仅在姿态尚未稳定时申请下一帧。
- 离屏、pagehide或标签隐藏会卸载Canvas；几何/材质/纹理显式释放。资产失败、超时或WebGL上下文丢失回静态，可由用户明确重试。GLB不允许加载远端贴图。

## 当前实测范围

使用Three真实GLTFLoader解析交付文件、检查节点/坐标/外部依赖/大小；纯动作状态与组件降级交互合计13项通过。组件测试用视觉替身，不是GPU渲染。模型有Blender真实海报，浏览器GPU、移动帧率与200%缩放尚待解锁实测。

依赖锁定：three 0.185.1、@react-three/fiber 9.7.0（MIT），@types/three 0.185.4（MIT）。React 19.2.8处于安装包peer范围 `>=19 <19.3`。参考：[Fiber官方介绍](https://r3f.docs.pmnd.rs/getting-started/introduction)、[Three官方文档](https://threejs.org/docs/)。只按需用Fiber和GLTFLoader，未引入整套Drei。

当前构建3D独立块927.67kB原始/247.66kB gzip，触发Vite默认500kB提示；保留警告，不提高阈值掩盖。入口包394.29kB原始/118.56kB gzip。还需真实弱网与设备检查，不能仅以gzip体积声称满足帧率预算。
