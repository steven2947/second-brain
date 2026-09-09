# 调研与借鉴记录

记录日期：2026-09-08。只把官方网页/仓库说明支持的能力写成事实；下面的“采用方式”是本项目设计判断，不是对方承诺兼容。Star数会变化，本包不靠未经核验的排名作选型依据。

## 产品与交互

| 来源 | 可参考的实践 | 本项目采用方式 | 不照搬的部分 |
| --- | --- | --- | --- |
| [Heptabase](https://heptabase.com/) | 知识卡、可视组织、资料与学习工作区的结合 | 书房→卡片→来源/关联；理解原理与解决问题相连；知识内容不是只藏在聊天里 | 不是购买其服务；首版不复制全自由白板，避免先搭复杂画布却没做好答案 |
| [assistant-ui](https://github.com/assistant-ui/assistant-ui) | 可组合React聊天组件，支持自定义后端与交互状态 | 评估使用其输入框、消息、动作栏等基础件，业务卡片和验证后事件自行适配 | 不照搬默认视觉；不为了组件默认流式协议改变安全契约；不需要其可选云服务 |
| [Karakeep](https://github.com/karakeep-app/karakeep) | 保存和组织个人知识资料的自托管体验 | 借鉴收藏、检索、卡片列表和整理路径 | 仓库AGPL许可需评估，不直接复制代码进协作产品；首版不接任意网页抓取 |
| [Onlook](https://docs.onlook.com/) | 面向React/Tailwind的可视化修改思路 | 将主题、文案、布局组件集中，未来可评估可视编辑器 | 本版不承诺零代码编辑全部业务，也不假定与选定Vite版本无缝兼容 |

assistant-ui官方仓库明确提供自定义runtime接入，并将MIT组件与可选云持久化区分；适合减轻基础聊天UI工作，不替代本项目鉴权、知识或模型服务。[官方说明](https://github.com/assistant-ui/assistant-ui)

## 3D与视觉实现

| 来源 | 参考内容 | 取舍 |
| --- | --- | --- |
| [React Three Fiber](https://github.com/pmndrs/react-three-fiber) | React与Three.js场景结合 | 将人物放在独立懒加载组件，业务页面不依赖WebGL成功 |
| [Drei PresentationControls](https://github.com/pmndrs/drei/blob/master/docs/controls/presentation-controls.mdx) | 展示对象拖动、角度限制及回弹控制 | 适合馆员展示；视线跟随与无障碍替代仍要另外实现 |

不把“网页上有个跟随鼠标的图”当真3D。源模型、GLB、材质、动画和许可都需要交付；参考仓库不自动提供本产品原创角色。

## 后端与安全

| 官方依据 | 对本项目的影响 |
| --- | --- |
| [Django认证](https://docs.djangoproject.com/en/5.2/topics/auth/) | 复用成熟认证基础；对象授权、产品角色和限流仍由本项目补齐 |
| [Django部署检查](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/) | 生产配置、秘密、HTTPS及检查流程单独验收 |
| [PostgreSQL行级安全](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) | 测实际运行角色，避免owner绕过制造假隔离 |
| [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/) | 组织鉴权、输入处理、数据保护和配置验证证据 |
| [OWASP提示词泄露风险](https://genai.owasp.org/llmrisk/llm072025-system-prompt-leakage/) | prompt不作为授权控制，公开输出与内部上下文分离 |

## 原项目与本地基线

用户指定的基础是 [steven2947/second-brain](https://github.com/steven2947/second-brain)。本轮公开网页工具访问该地址返回404，可能与访问范围或仓库状态有关，**不能据此断言仓库被删，也不宣称已核验远端最新源码**。本包依据本机协作工作树 `e74bf5f` 的实际源码与schema设计，不悄悄换成另一个同名项目。

本机重点核对：`src/orchestration/intake.py`、`session.py`、`adoption.py`、`validation.py`，以及问题、事件、请求和v3草稿schema。已有Grilling参考文件和五轮兼容逻辑继续复用；本轮不是重新下载安装Grilling或仓颉。固定五类题当前仍标rework_required。

新增部分是身份与权限、Web持久化、异步模型服务、公开答案投影、页面、学习行动闭环、运维。它们不是原CLI已经具有的完整网络服务；不能把仓颉蒸馏、卡片资产、Skill规则和在线模型服务混称为一个东西。

## 调研结论

最值得结合的不是再引入一个大框架，而是四件具体事：卡片与来源可探索；聊天组件可组合；权限/任务由后端可靠执行；馆员与主题独立可替换。先做一条真实有效的问题闭环，再增加学习与资产组织；不先做无限画布或堆叠没有证据的专家头像。

实施时对实际选入的依赖重新核验版本、许可、安全状态与兼容性，并锁版本。调研链接不是安装命令，本轮没有下载运行这些第三方项目。
