"""把 Agent 蒸馏输出装配为证据可验证的候选书库，不把格式验证当语义复核。"""
import hashlib
import re
from pathlib import Path
from src.distillation.normalize import verify_span
from src.distillation.jobs import write_json
from src.knowledge.library import read_json, validate_library


def assemble_library(document_path, output_paths, destination):
    """装配候选；document_path 为规范化文档，output_paths 为各组审阅输出，destination 必须不存在。"""
    document = read_json(document_path); book = document['book']; destination = Path(destination)
    if destination.exists():
        raise ValueError('DESTINATION_EXISTS: 候选目录已存在，请使用新目录')
    paragraphs = {p['id']:p for p in document['paragraphs']}
    namespace = book['book_id'].removeprefix('book.')
    if not re.fullmatch(r'[a-z0-9-]+',namespace):
        raise ValueError('INVALID_CANDIDATE: book_id 命名空间无效')
    original = (Path(document_path).parent/'source.md').read_bytes().decode('utf-8')
    for p in paragraphs.values():
        if not re.fullmatch(r'[a-z0-9.-]+',p['id']):
            raise ValueError('INVALID_CANDIDATE: 段落 ID 无效')
        verify_span(original,document['source_sha256'],p['start'],p['end'],p['text'])
    expected = {p['section_id'] for p in document['paragraphs']}
    outputs = [read_json(path) for path in output_paths]
    reviewed = {s for output in outputs for s in output['sections_reviewed']}
    if reviewed != expected:
        raise ValueError(f'INCOMPLETE_COVERAGE: 未覆盖 {sorted(expected-reviewed)}，未知 {sorted(reviewed-expected)}')
    drafts = [card for output in outputs for card in output['cards']]
    slugs = [card['slug'] for card in drafts]
    if any(not isinstance(slug,str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',slug) for slug in slugs):
        raise ValueError('INVALID_CANDIDATE: slug 格式无效')
    if len(set(slugs)) != len(slugs):raise ValueError('INVALID_CANDIDATE: slug 重复')
    used = set()
    for draft in drafts:
        ids = draft['evidence_paragraph_ids'] + [c['paragraph_id'] for c in draft.get('source_cases',[])]
        if not ids or any(key not in paragraphs for key in ids):
            raise ValueError(f"INVALID_CANDIDATE: {draft['slug']} 原文 ID 无效")
        used.update(ids)
    relations = [edge for output in outputs for edge in output.get('relations',[])]
    for edge in relations:
        if edge['from_slug'] not in slugs or edge['to_slug'] not in slugs:
            raise ValueError('INVALID_CANDIDATE: 关系卡片不存在')
        if any(key not in paragraphs for key in edge['evidence_paragraph_ids']):
            raise ValueError('INVALID_CANDIDATE: 关系证据不存在')
        used.update(edge['evidence_paragraph_ids'])
    # 交付证据汇编仅包含被采用段落；不复制整本原书，另保留原文位置。
    corpus = '# 引用证据汇编\n\n以下段落是离散的证据片段，排列相邻不表示原书相邻。\n\n'
    evidence = []
    for key in sorted(used, key=lambda k:paragraphs[k]['start']):
        p = paragraphs[key]
        corpus += f"## {key} · {p['chapter']}\n\n"
        start = len(corpus);corpus += p['text'];end = len(corpus);corpus += '\n\n'
        evidence.append({'schema_version':1,'id':'evidence.'+key,'book_id':book['book_id'],
                         'chapter':p['chapter'],'source_path':'sources/evidence.md','start':start,'end':end,'text':p['text'],
                         'origin':{'source_sha256':document['source_sha256'],'paragraph_id':key,'start':p['start'],'end':p['end']}})
    source_hash = hashlib.sha256(corpus.encode()).hexdigest()
    destination.mkdir(parents=True)
    (destination/'sources').mkdir();(destination/'sources/evidence.md').write_text(corpus,encoding='utf-8')
    for ev in evidence:
        ev['source_sha256'] = source_hash;write_json(destination/'evidence'/f"{ev['id']}.json",ev)
    cards = []
    for draft in drafts:
        keys = ['title','kind','statement','reasoning','conditions','boundaries','steps','application_notes',
                'keywords','trigger_questions','source_cases','source_claim_type']
        card = {key:draft[key] for key in keys if key in draft}
        card.update(schema_version=1,id=f'knowledge.{namespace}.'+draft['slug'],book_id=book['book_id'],author_id=book['author_id'])
        all_ids = list(dict.fromkeys(draft['evidence_paragraph_ids']+[c['paragraph_id'] for c in draft.get('source_cases',[])]))
        card['evidence_ids'] = ['evidence.'+key for key in all_ids]
        cards.append(card);write_json(destination/'cards'/f"{draft['slug']}.json",card)
    edges = [{'id':f'relation.{namespace}.{i:03d}','from':f'knowledge.{namespace}.'+e['from_slug'],'to':f'knowledge.{namespace}.'+e['to_slug'],
              'type':e['type'],'basis':e['basis'],'rationale':e['rationale'],
              'evidence_ids':['evidence.'+key for key in e['evidence_paragraph_ids']]} for i,e in enumerate(relations)]
    write_json(destination/'relations.json',{'schema_version':1,'edges':edges})
    coverage = [{**s,'status':'agent_reviewed' if s['paragraph_ids'] else 'structural_heading',
                 'cited_paragraph_count':sum(key in used for key in s['paragraph_ids'])} for s in document['sections']]
    write_json(destination/'coverage.json',{'source_sha256':document['source_sha256'],'sections':coverage,
               'excluded_sections':document['excluded_sections'], 'review_method':'完整分组阅读、自检及根 Agent 抽样复核；非独立人工审计'})
    manifest_book = {key:book[key] for key in ('title','author_id','author','compiler','translator','edition') if key in book}
    manifest_book.update(id=book['book_id'],status='agent_reviewed_pilot',source_sha256=document['source_sha256'],
                         source_chars=len(original),scope=book.get('scope_rationale',''),paragraph_count=len(paragraphs),section_count=len(coverage))
    write_json(destination/'manifest.json',{'schema_version':1,'library_id':f'library.{namespace}-pilot','is_example':False,
               'books':[manifest_book], 'cards_directory':'cards','evidence_directory':'evidence','relations_file':'relations.json',
               'distillation_mode':'agent_managed','semantic_audit':'agent_self_review_plus_root_sampling',
               'field_semantics':{'statement':'有出处的概括，作者归属见 source_claim_type',
                 'reasoning':'依据正文整理的解释，不是逐字原话',
                 'conditions_boundaries_steps':'含 Agent 编排与应用限制，须结合 application_notes，不能整体归为作者明确程序',
                 'author_id':'本书主要观点人物；quoted_other 仍需保留第三方署名',
                 'origin':'装配时与原书逐字校验；分发库仅验证映射一致性，重新核验原书需另提供同指纹原文件'}})
    report = validate_library(destination)
    return {**report,'path':str(destination.resolve()),'covered_sections':len(coverage),'paragraphs':len(paragraphs)}
