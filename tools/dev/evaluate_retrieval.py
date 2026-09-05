"""对预先固定的问题集比较召回；命中率不代表完整问答正确率。"""
import argparse
import hashlib
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from src.knowledge.library import Library, read_json
from src.retrieval.search import SearchEngine
from src.distillation.jobs import write_json


def evaluate(library_root, cases_path, index_root):
    """library_root 为待评估库，cases_path 为已固定标签，index_root 保存可重建向量。"""
    library = Library(library_root)
    engine = SearchEngine(library,Path(index_root),Path(index_root)/'model-cache')
    rows = [];totals = {}
    for case in read_json(cases_path)['cases']:
        variants = {}
        for label, mode, expansions in [('keyword','keyword',[]),('semantic','semantic',[]),
                                        ('hybrid','hybrid',[]),('hybrid_expanded','hybrid',case.get('expansions',[]))]:
            started = time.perf_counter()
            results = engine.search(case['question'],mode=mode,expansions=expansions,limit=5)
            slugs = [r['card']['id'].split('.')[-1] for r in results]
            expected = case['expected']
            passed = any(slug in slugs for slug in expected) if expected else not results
            variants[label] = {'passed':passed,'seconds':round(time.perf_counter()-started,3),
                               'top5':[{'id':r['card']['id'],'title':r['card']['title'],
                                        'similarity':r['semantic_similarity']} for r in results]}
            counter = totals.setdefault(label,{'positive_hits':0,'positive_cases':0,'negative_rejections':0,'negative_cases':0})
            if expected:
                counter['positive_cases']+=1;counter['positive_hits']+=int(passed)
            else:
                counter['negative_cases']+=1;counter['negative_rejections']+=int(passed)
        rows.append({**case,'variants':variants})
    return {'library_version':library.version,'cases_sha256':hashlib.sha256(Path(cases_path).read_bytes()).hexdigest(),
            'model':'BAAI/bge-small-zh-v1.5','threshold':0.45,'totals':totals,'cases':rows,
            'limits':'小样本同开发者标签；只测前五命中及空结果，未测完整回答、独立用户效果或大书库扩展'}


def main():
    """读取 CLI 路径参数并保存可复核结果。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',default='data/library')
    parser.add_argument('--cases',default='tests/naval-retrieval-holdout.json')
    parser.add_argument('--indexes',default='data/indexes')
    parser.add_argument('--out',required=True)
    args = parser.parse_args()
    report = evaluate(args.library,args.cases,args.indexes)
    write_json(args.out,report)
    print(report['totals'])


if __name__ == '__main__':
    main()
