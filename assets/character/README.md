# 原创 3D 馆员

本批为项目单独编写参数化建模脚本制作的原创风格化人物：森林绿开衫、米白裤、黄铜细圆眼镜、打开的书、问候手势。没有导入第三方人物、网格、贴图或动作；没有以静态图代替可旋转模型。原有 `librarian-concept-v1.png` 继续保留，当前人物是独立设计，**不是该概念图的精确三维重建**。

## 文件与重建

- `build_librarian.py`：唯一建模与导出脚本；所有几何和 PBR 色材质均由此生成。
- `librarian.blend`：可编辑网格、材质、层级和摄影棚场景；相机、光源与地面不导出到网页。
- `../../web/public/models/librarian.glb`：网页自包含 glTF 2.0 模型。
- `../../web/public/images/librarian-poster-v1.png`：此模型的 Cycles 真实渲染，800 × 1000，48 samples。前端也可用其降级展示。
- `LICENSE.md`：原创来源、项目交付范围和工具许可说明。

从项目根目录运行：

```sh
.runtime/model-tools/Blender.app/Contents/MacOS/Blender \
  --background --factory-startup --python assets/character/build_librarian.py
```

脚本重建上述三个派生文件，并在标准输出打印 `GLB_VALIDATION` 与 `LIBRARIAN_BUILD`。不改概念图、原书、原提示词及产品数据。可用自己已安装的 Blender 4.5 执行同一脚本；工具目录不随项目分发。

本机 Blender 在受限执行沙箱中初始化 Metal 设备时曾崩溃，正常后台执行已成功；未禁用 Gatekeeper、未移除 quarantine、未安装系统服务或修改 `/Applications`。官方镜像仅只读挂载到项目 `.runtime/model-tools/blender-mount`，复制后该挂载已卸载。

## 工具来源与校验

制作工具为 Blender **4.5.13 LTS**, build `daeeeca98fb0`，macOS ARM64。2026-09-08 从 Blender 官方 HTTPS 获取：

- [官方包](https://download.blender.org/release/Blender4.5/blender-4.5.13-macos-arm64.dmg)
- [官方 SHA256 清单](https://download.blender.org/release/Blender4.5/blender-4.5.13.sha256)

下载包实际 SHA256 与官方清单相符：

```text
663ce944257c61ff1d6aa09e15c8f57bbd8d59023adb2fa7edde33a9ed960b53
```

下载包、清单、工具和构建日志保留在已被 git 忽略的 `.runtime/model-tools/`，没有提交或推送。

## 前端坐标与动作接口

Blender 制作源为 Z-up、-Y 朝前；导出时转为 glTF Y-up、+Z 朝前。模型脚底 Y=0，高约 3.072 单位。根节点无整体旋转或缩放。

| glTF 节点 | 枢轴与用途 | 建议前端局部动画 |
| --- | --- | --- |
| `Librarian` | 世界原点，整个角色 | 围绕 Y 轻转身 |
| `Head` | 世界 `[0, 2.02, 0]`，含脸、头发、眼镜 | Y 转头，X 点头 |
| `WaveArm` | 世界 `[0.36, 1.85, 0]`，含问候袖与手 | Z 小幅摆动 |
| `BookPage` | `OpenBook` 子节点，局部 `[0, 0.045, 0]`，位于书脊 | Y 翻页；片页有真实薄厚 |

没有内置动画 clip 或骨骼，前端在节点原始姿态上加小角度偏移。头部与右臂是刚性分组，可实现轻问候；不适合全身走路或大幅肢体变形。

正面展示可用 perspective camera `[0, 1.65, 6.8]`，lookAt `[0, 1.48, 0]`，FOV 32。网页可自行添加地面接触阴影，不需要额外地台。海报采用三分之四视角和柔和摄影棚光；网页光照不同会改变观感。

## 实际资产验证（2026-09-08）

脚本解析导出 GLB 的实际文件头、JSON、节点 TRS、POSITION bounds 和 accessor 索引；没有把源场景计数当作网页文件统计。导出日志无 WARNING/ERROR。最终海报已本地打开目检，修复了首版的衣领/裤腰穿插和翻页片重复面。

| 项目 | 结果 |
| --- | --- |
| 文件头 | `glTF`, version 2，声明长度与文件长度一致 |
| GLB 大小 | 1,333,852 bytes，低于 3 MB |
| 节点 / 网格 / 材质 | 101 / 96 / 17 |
| 顶点 / 三角形 | 36,077 / 64,192 |
| 纹理 / 外部 URI | 0 / 0；所有材质在 GLB 内 |
| X bounds | `[-0.69306, 0.89500]` |
| Y bounds | `[0.00000, 3.07194]` |
| Z bounds | `[-0.40596, 0.82509]` |
| GLB SHA256 | `6fb6fa236c32cb6a93f8f1add35e0ca0e18ed30ed6d678e0450ba6eabd4e0f14` |
| Poster SHA256 | `43f40ca07e867432b3744f49827057c0812b8b09573cc3aac867c2f489f4365c` |

该检查证明文件、结构及真实渲染一致；浏览器 WebGL 加载、移动设备帧率和前端动作仍由前端集成验收覆盖，不据此声称已通过实机 GPU 验收。
