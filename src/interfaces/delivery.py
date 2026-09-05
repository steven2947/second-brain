"""显式白名单构建本地试用包，不把开发工作区整体打包。"""
import hashlib
import json
import re
import zipfile
from pathlib import Path
from src.knowledge.library import Library


def build_release(project, destination, library_root=None, author_skill=None):
    """project 为项目根，destination 为新 zip；library_root 与 author_skill 显式指定要随包交付的资产。"""
    project, destination = Path(project).resolve(), Path(destination).resolve()
    if destination.exists():raise ValueError('DESTINATION_EXISTS: 不覆盖已有交付包')
    library = Library(library_root or project/'examples/sample-library')
    roots = [(project/'src','src'),(project/'schemas','schemas'),
             (project/'skills/second-brain','skills/second-brain'),(project/'prompts','prompts'),
             (library.root,'seed-library')]
    upstream = project/'vendor/cangjie'
    roots.extend((upstream/name,'vendor/cangjie/'+name) for name in ['scripts','schemas','methodology','extractors','templates','docs'])
    singles = [(project/'requirements-mvp.lock.txt','requirements.txt'),
               (project/'docs/distillation-workflow.md','docs/distillation-workflow.md'),
               (project/'docs/usage.md','docs/usage.md'),
               (project/'vendor/cangjie.lock.json','vendor/cangjie.lock.json'),
               (upstream/'SKILL.md','vendor/cangjie/SKILL.md'),(upstream/'LICENSE','vendor/cangjie/LICENSE')]
    if author_skill:roots.append((Path(author_skill),'skills/'+Path(author_skill).name))
    files = {}
    for root, prefix in roots:
        if not root.is_dir():raise ValueError(f'MISSING_DELIVERY_INPUT: {prefix}')
        for source in sorted(root.rglob('*')):
            if source.is_symlink():raise ValueError('INVALID_DELIVERY: 不接受符号链接')
            rel = source.relative_to(root)
            if any(part in ('.git','__pycache__','.pytest_cache') for part in rel.parts):continue
            if source.is_file() and source.suffix not in ('.pyc','.pyo') and source.name != '.DS_Store':
                files[prefix+'/'+rel.as_posix()] = source.read_bytes()
    for source,name in singles:files[name] = source.read_bytes()
    readme = '''# 第二大脑本地单书试用包

Python 3.12；本包提供书籍知识、关键词/本地向量/混合查询、证据与图谱接口、问答 Skill 和仓颉蒸馏工具。
正文蒸馏仍由 Agent 执行提示词，脚本负责准备、装配、验证和发布；不是自动模型调用服务。

## 安装与初始化

在解压目录创建环境并安装依赖：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m src.interfaces.cli --library "$HOME/SecondBrainData/library" publish seed-library
.venv/bin/python -m src.interfaces.cli --library "$HOME/SecondBrainData/library" books
.venv/bin/python -m src.interfaces.cli --library "$HOME/SecondBrainData/library" search '怎样选择值得长期投入的方向' --mode keyword
```

将 mode 改为 hybrid 可启用本地中文向量；首次只下载模型文件，文本在本地计算。Agent 读取 skills/second-brain/SKILL.md，并使用实际用户库路径执行查询。

## 扩充书籍

按照 vendor/cangjie/SKILL.md 与 prompts/distillation/ 处理用户提供的正文。CLI prepare 生成带指纹和段落 ID 的任务；Agent 输出知识候选后使用 assemble、validate 和 publish。详细参数可运行子命令 --help。

## 升级与数据保留

将新版程序解压到新目录，继续使用同一外部用户数据目录。不要在升级时删除 SecondBrainData，不自动重新发布 seed-library。原书、个人配置与模型缓存不随本包复制。

## 边界

书库清单说明具体书籍与审阅范围。证据汇编是离散片段，不等于完整原书。评分不是事实置信度；未找到支持时说明不足。多作者综合、自动批量模型执行和云端服务尚未验证。
'''
    files['README.md'] = readme.encode()
    # 扫描实际内容，拦截常见本机绝对路径；不扫描仅根据根目录猜测。
    for name, content in files.items():
        if name.startswith(('src/','schemas/','skills/','seed-library/','prompts/')) and re.search(rb'/(?:Users/[A-Za-z0-9._-]+|private/var/folders)/',content):
            raise ValueError(f'PRIVATE_PATH_IN_DELIVERY: {name}')
    checksums = {name:hashlib.sha256(content).hexdigest() for name,content in files.items()}
    files['BUILD_MANIFEST.json'] = json.dumps({'schema_version':1,'library_version':library.version,
        'is_example':library.manifest.get('is_example',False),'files':checksums},ensure_ascii=False,indent=2).encode()
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,content in sorted(files.items()):archive.writestr('second-brain-mvp/'+name,content)
    return {'path':str(destination),'files':len(files),'bytes':destination.stat().st_size,
            'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'library_version':library.version}
