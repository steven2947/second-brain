"""将经审阅的少量方法编译为仓颉 Capability Bundle，普通知识仍留在书库。"""
from pathlib import Path
import shutil
import hashlib
from src.knowledge.library import Library, read_json
from src.distillation.jobs import write_json


def build_cangjie_bundle(library_root, output_paths, destination):
    """library_root 为已验收库，output_paths 提供三重验证记录，destination 为全新 Bundle 目录。"""
    import yaml
    library = Library(library_root); book = library.manifest['books'][0]
    namespace = book['id'].removeprefix('book.')
    destination = Path(destination)
    if destination.exists():raise ValueError('DESTINATION_EXISTS: Bundle 已存在')
    candidates = [c for path in output_paths for c in read_json(path).get('cangjie_candidates',[])
                  if c.get('promotion_decision') == 'approved']
    if not candidates:raise ValueError('NO_CAPABILITIES: 暂无通过三重验证的方法')
    capabilities = []; reviews = []
    for candidate in candidates:
        slug = candidate['slug'];card = library.get_knowledge(f'knowledge.{namespace}.{slug}')
        ids = candidate['V1']['paragraph_ids']
        if len(set(ids)) < 2 or not card.get('source_cases'):
            raise ValueError(f'INVALID_CAPABILITY: {slug} 缺少双语境依据或书中案例')
        for pid in ids:library.get_evidence('evidence.'+pid)
        if not candidate['V2'].get('new_question') or not candidate['V3'].get('reason'):
            raise ValueError('INVALID_CAPABILITY: 三重验证记录不完整')
        ev = library.get_evidence(card['evidence_ids'][0])
        reading = ev['text'][:140]
        interpretation = '\n\n'.join([card['statement'],card.get('reasoning','')])
        cases = '\n'.join('- '+case['summary']+'（'+case['paragraph_id']+'）' for case in card['source_cases'])
        triggers = '\n'.join('- '+q for q in card.get('trigger_questions',[]))
        steps = '\n'.join(f'{i}. {step}' for i,step in enumerate(card.get('steps',[]),1))
        boundaries = '\n'.join('- '+s for s in card.get('boundaries',[]))
        body = f"# {card['title']}\n\n## R — 原文\n\n> {reading}\n\n出处：《{book['title']}》，{ev['chapter']}；{ev['origin']['paragraph_id']}。\n\n## I — 解释\n\n{interpretation}\n\n## A1 — 书中案例\n\n{cases}\n\n## A2 — 触发与区分\n\n{triggers}\n\n仅在问题符合适用条件时使用；与相邻能力的区别以原书条件为准。\n\n## E — 执行\n\n{steps}\n\n{card.get('application_notes','具体行动属于对书中方法的应用。')}\n\n## B — 边界\n\n{boundaries}\n\n不能替代实时事实或当前专业判断；引用必须回到当前书库证据。\n"
        path = destination/'cards'/f'{slug}.md';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body,encoding='utf-8')
        capabilities.append({'capability_id':f'cap.{namespace}.{slug}','revision':1,'status':'active',
            'slug':slug,'title':card['title'],'importance':'high','importance_rationale':'审阅记录包含独立语境、应用问题与边界，优先服务本书实际问题分析',
            'one_liner':card['statement'],'intents':card.get('trigger_questions') or [card['title']],
            'keywords':card.get('keywords') or [card['title']],'also_read':[],'card':f'cards/{slug}.md',
            'frontmatter':{'description':'用户遇到以下问题时参考本书方法：'+ '；'.join(card.get('trigger_questions',[]))+'。不用于实时事实查询或脱离适用条件的结论。'},
            'source_evidence':[{'source_id':book['id'],'version_id':book['source_sha256'],'location':library.get_evidence('evidence.'+pid)['chapter'],'chunk_ids':[pid]} for pid in ids],
            'promotion':{'destination':'router','notes':'单书 MVP 只交付一个入口，不创建多余独立方法 Skill'}})
        reviews.append(candidate)
    cap_slugs = {cap['slug'] for cap in capabilities}
    for cap in capabilities:
        cap['also_read'] = sorted({r['target']['id'].split('.')[-1] for r in library.get_related(f"knowledge.{namespace}.{cap['slug']}") if r['target']['id'].split('.')[-1] in cap_slugs})
    entry = {'name':namespace,'description':f"当用户希望依据《{book['title']}》中的已审阅方法分析实际问题时使用，先检查条件与原文证据，再提出明确标记为应用推断的行动建议。知识范围限本书，不代表作者全部观点。",
             'core_principles':[cap['one_liner'] for cap in capabilities[:7]],
             'out_of_scope':['实时行情、医疗处置和本书未覆盖的事实','冒充作者本人作出承诺'],
             'stop_conditions':['找不到支持证据时说明覆盖不足','原文与引用版本不一致时先重新核验']}
    # 不硬造核心原则以满足格式；少于三项时拒绝生成夸大的作者入口。
    if len(entry['core_principles'])<3:raise ValueError('NO_CAPABILITIES: 至少需要三项已审阅核心方法')
    bundle = {'schema_version':1,'bundle_id':'bundle.'+namespace,'book':{'title':book['title'],'author':book['author'],'source_pack':namespace},
              'entry':entry,'router_entry':{'name':namespace,'description':entry['description']},'promotion_budget':8,'capabilities':capabilities}
    (destination/'verified.yaml').write_text(yaml.safe_dump(bundle,allow_unicode=True,sort_keys=False),encoding='utf-8')
    write_json(destination/'destinations.json',{'bundle_id':bundle['bundle_id'],'destinations':{c['capability_id']:{'served_by':namespace} for c in capabilities}})
    write_json(destination/'triple-review.json',{'reviews':reviews,'method':'Agent 提取与根 Agent 抽样核验；非独立人工审计'})
    (destination/'book').mkdir()
    (destination/'book/overview.md').write_text('# 全书范围\n\n'+book.get('scope','')+'\n\n本入口只包含通过方法筛选的部分；其他知识仍由主书库检索。',encoding='utf-8')
    (destination/'book/glossary.md').write_text('# 术语\n\n'+'\n\n'.join('## '+c['title']+'\n'+c['statement'] for c in library.cards.values() if c['kind']=='definition'),encoding='utf-8')
    return {'capabilities':len(capabilities),'path':str(destination.resolve())}


def build_author_skill(library_root, compiled_root, destination):
    """将 compiled_root 的仓颉参考卡接入 library_root 查询；destination 为新作者 Skill 目录。"""
    library = Library(library_root);book = library.manifest['books'][0]
    destination, compiled_root = Path(destination), Path(compiled_root)
    if destination.exists():raise ValueError('DESTINATION_EXISTS: 作者 Skill 已存在')
    source_entry = (compiled_root/'SKILL.md').read_bytes()
    if not (compiled_root/'references').is_dir():raise ValueError('INVALID_COMPILED_SKILL: 缺少引用卡')
    destination.mkdir(parents=True)
    shutil.copytree(compiled_root/'references',destination/'references')
    content = f'''---
name: {book['id'].removeprefix('book.')}
description: 当用户希望借助《{book['title']}》及{book['author']}在本书中的观点分析实际问题时使用；涵盖本书已蒸馏知识，回答前查询书库证据并检查适用条件。
---

# 《{book['title']}》作者视角

你使用本书证据帮助用户思考，不扮演作者本人，不代表作者全部作品或当前意见。本书编著者为{book.get('compiler','清单所列编著者')}，主要观点人物为{book['author']}；第三方引语保留署名。

先读取同级 `../second-brain/SKILL.md` 与查询工作流，确认程序根目录和实际用户库路径。调用 `books` 确认当前版本包含 `{book['id']}`；这份入口编译时的版本为 `{library.version}`，当前库变化后以当前证据为准。

1. 从用户目标、条件与待决定事项拆解问题；保留原问题并补充少量概念问法。
2. 使用 `search`，按 `--book {book['id']}` 过滤；读取 `knowledge`、`evidence` 和相关 `related` 结果。覆盖范围和数量以当前清单为准。
3. 分别给出书中观点、适用条件、与当前情境的联系、系统推导的小步行动及引用。对互相牵制的观点保留条件差异。
4. 检索没有支持就说明书库覆盖不足；用户要其他作者比较时交回通用 Skill，不虚构第二位作者已入库。

`references/capabilities/` 是仓颉筛选的方法参考，先核对当前知识库再使用。方法卡只是全库的一部分，未命中方法路由不代表整本书没有相关知识。概览和术语也需当前库证据，不能仅凭速查表回答事实。

书中出现第三方署名或正文语境差异时，不按作者名一概归属。具体提问模板、步骤与边界可能包含系统编排，不能加引号当作者原话。
'''
    (destination/'SKILL.md').write_text(content,encoding='utf-8')
    write_json(destination/'ADAPTATION.json',{'library_version':library.version,
        'upstream_entry_sha256':hashlib.sha256(source_entry).hexdigest(),
        'changes':'替换入口为库查询协议，保留仓颉能力参考卡；不沿用上游原产物校验清单'})
    return {'path':str(destination.resolve()),'library_version':library.version}
