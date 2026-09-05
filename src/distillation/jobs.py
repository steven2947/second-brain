"""可复用的蒸馏准备与状态缓存；不调用模型、不覆盖已有 Agent 输出。"""
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from src.distillation.normalize import normalize_markdown


def write_json(path, value):
    """原子写 JSON；path 为目标，value 为可序列化对象。"""
    path = Path(path);path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.json-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2);stream.write('\n')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def prepare_job(source, scope, jobs_root, prompts_root, executor='current-agent'):
    """准备正文任务；source 为书文件，scope 为范围配置，两个 root 分别保存任务和读取提示词。"""
    source, jobs_root, prompts_root = Path(source), Path(jobs_root), Path(prompts_root)
    raw = source.read_bytes()
    digest = hashlib.sha256(raw)
    digest.update(json.dumps(scope, ensure_ascii=False, sort_keys=True).encode())
    digest.update(executor.encode())
    for path in sorted(prompts_root.glob('*.md')):
        digest.update(path.name.encode());digest.update(path.read_bytes())
    # 正文处理实现改变后，新任务不会复用旧位置映射。
    digest.update(Path(__file__).with_name('normalize.py').read_bytes())
    job_id = digest.hexdigest()[:24]; root = jobs_root / job_id
    if (root/'state.json').is_file():
        return {'job_id': job_id, 'path': str(root.resolve()), 'reused': True}
    jobs_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.prepare-', dir=jobs_root))
    try:
        document = normalize_markdown(raw.decode('utf-8'), scope['included_ranges'])
        document['book'] = scope
        write_json(temporary/'document.json', document)
        (temporary/'source.md').write_bytes(raw)
        paragraphs = {p['id']: p for p in document['paragraphs']}
        units = []
        for section in document['sections']:
            unit = {**section, 'paragraphs': [paragraphs[key] for key in section['paragraph_ids']]}
            if unit['paragraphs']:
                write_json(temporary/'units'/f"{section['id']}.json", unit)
            units.append({'section_id': section['id'], 'title': section['path'],
                          'status': 'awaiting_agent' if unit['paragraphs'] else 'structural_heading',
                          'paragraph_count': len(unit['paragraphs'])})
        write_json(temporary/'state.json', {'schema_version':1, 'job_id':job_id,
                   'source_sha256':document['source_sha256'], 'executor':executor,
                   'created_at':datetime.now(timezone.utc).isoformat(), 'status':'awaiting_agent',
                   'input_tokens':None,'output_tokens':None,'cost':None,'units':units})
        if root.exists():
            raise ValueError('JOB_EXISTS_INCOMPLETE: 保留已有不完整任务供检查')
        os.replace(temporary, root)
    finally:
        if temporary.exists():shutil.rmtree(temporary)
    return {'job_id':job_id, 'path':str(root.resolve()), 'reused':False}


def complete_job(job_root, output_paths, candidate):
    """登记已装配任务；job_root 为准备目录，output_paths 为审阅输出，candidate 为待登记知识库。"""
    from src.knowledge.library import read_json, content_version, validate_library
    from src.distillation.assemble import assemble_library
    job_root, candidate = Path(job_root), Path(candidate)
    state = read_json(job_root/'state.json')
    validate_library(candidate)
    # 从任务自身的正文重装配，防止把其他任务或被改过的产物登记为已完成。
    with tempfile.TemporaryDirectory(prefix='verify-job-') as temporary:
        reconstructed = Path(temporary)/'candidate'
        assemble_library(job_root/'document.json',output_paths,reconstructed)
        if content_version(reconstructed) != content_version(candidate):
            raise ValueError('JOB_OUTPUT_MISMATCH: 候选不匹配本任务正文及输出')
    if state.get('status') == 'completed':
        if state.get('candidate_version') != content_version(candidate):
            raise ValueError('JOB_ALREADY_COMPLETED: 使用新任务保留旧记录')
        return {'job_id':state['job_id'],'reused':True,'candidate_version':state['candidate_version']}
    hashes = {}
    for index,path in enumerate(output_paths):
        raw = Path(path).read_bytes();name = f'outputs/group-{index:03d}.json'
        target = job_root/name;target.parent.mkdir(exist_ok=True)
        if target.exists() and target.read_bytes() != raw:
            raise ValueError('JOB_OUTPUT_EXISTS: 不覆盖已登记输出')
        target.write_bytes(raw);hashes[name] = hashlib.sha256(raw).hexdigest()
    for unit in state['units']:
        if unit['paragraph_count']:unit['status'] = 'agent_reviewed'
    state.update(status='completed',completed_at=datetime.now(timezone.utc).isoformat(),
                 candidate_version=content_version(candidate),output_sha256=hashes,
                 semantic_audit='agent_self_review_plus_root_sampling')
    write_json(job_root/'state.json',state)
    return {'job_id':state['job_id'],'reused':False,'candidate_version':state['candidate_version']}
