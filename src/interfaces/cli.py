"""第二大脑本地 CLI；只读查询与显式蒸馏准备、验证、发布分开。"""
import argparse
import json
import sys
from pathlib import Path
from src.knowledge.library import Library, validate_library, publish_library, read_json
from src.retrieval.search import SearchEngine
from src.distillation.jobs import prepare_job, complete_job
from src.distillation.assemble import assemble_library


def main(argv=None):
    """解析 argv 并执行明确命令；失败返回 JSON 错误和非零退出码。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',default='data/library',help='版本库或单版本目录')
    parser.add_argument('--index-root',default=None,help='向量与模型本地缓存目录')
    commands = parser.add_subparsers(dest='command',required=True)
    books = commands.add_parser('books');books.add_argument('--author')
    search = commands.add_parser('search');search.add_argument('query');search.add_argument('--mode',choices=['keyword','semantic','hybrid'],default='hybrid')
    search.add_argument('--book');search.add_argument('--author');search.add_argument('--limit',type=int,default=5)
    search.add_argument('--expand',action='append',default=[]);search.add_argument('--min-similarity',type=float,default=0.45)
    knowledge = commands.add_parser('knowledge');knowledge.add_argument('id')
    evidence = commands.add_parser('evidence');evidence.add_argument('id');evidence.add_argument('--context',type=int,default=0)
    related = commands.add_parser('related');related.add_argument('id');related.add_argument('--type');related.add_argument('--hops',type=int,default=1);related.add_argument('--direction',choices=['in','out','both'],default='both')
    validate = commands.add_parser('validate');validate.add_argument('path')
    publish = commands.add_parser('publish');publish.add_argument('candidate')
    prepare = commands.add_parser('prepare');prepare.add_argument('--source',required=True);prepare.add_argument('--scope',required=True);prepare.add_argument('--jobs-root',default='data/jobs/prepared');prepare.add_argument('--prompts-root',default='prompts/distillation')
    assemble = commands.add_parser('assemble');assemble.add_argument('--document',required=True);assemble.add_argument('--output',action='append',required=True);assemble.add_argument('--destination',required=True)
    complete = commands.add_parser('complete');complete.add_argument('--job',required=True);complete.add_argument('--output',action='append',required=True);complete.add_argument('--candidate',required=True)
    bundle = commands.add_parser('bundle');bundle.add_argument('--review',action='append',required=True);bundle.add_argument('--destination',required=True)
    author_skill = commands.add_parser('author-skill');author_skill.add_argument('--compiled',required=True);author_skill.add_argument('--destination',required=True)
    package = commands.add_parser('package');package.add_argument('--project',default='.');package.add_argument('--destination',required=True);package.add_argument('--author-skill')
    args = parser.parse_args(argv)
    try:
        version = None
        if args.command == 'validate':result = validate_library(args.path)
        elif args.command == 'publish':result = publish_library(args.candidate,args.library)
        elif args.command == 'prepare':result = prepare_job(args.source,read_json(args.scope),args.jobs_root,args.prompts_root)
        elif args.command == 'assemble':result = assemble_library(args.document,args.output,args.destination)
        elif args.command == 'complete':result = complete_job(args.job,args.output,args.candidate)
        elif args.command == 'bundle':
            from src.distillation.cangjie_adapter import build_cangjie_bundle
            result = build_cangjie_bundle(args.library,args.review,args.destination)
        elif args.command == 'author-skill':
            from src.distillation.cangjie_adapter import build_author_skill
            result = build_author_skill(args.library,args.compiled,args.destination)
        elif args.command == 'package':
            from src.interfaces.delivery import build_release
            result = build_release(args.project,args.destination,args.library,args.author_skill)
        else:
            library = Library(args.library);version = library.version
            if args.command == 'books':result = library.list_books(args.author)
            elif args.command == 'knowledge':result = library.get_knowledge(args.id)
            elif args.command == 'evidence':result = library.get_evidence(args.id,args.context)
            elif args.command == 'related':result = library.get_related(args.id,args.type,args.hops,args.direction)
            else:
                index_root = Path(args.index_root) if args.index_root else Path(args.library).resolve().parent/'indexes'
                result = SearchEngine(library,index_root,index_root/'model-cache').search(args.query,args.mode,args.book,args.author,args.limit,args.expand,args.min_similarity)
        print(json.dumps({'schema_version':1,'library_version':version,'result':result},ensure_ascii=False,indent=2));return 0
    except (ValueError,OSError,KeyError,TypeError,RuntimeError) as exc:
        print(json.dumps({'schema_version':1,'error':str(exc)},ensure_ascii=False),file=sys.stderr);return 2


if __name__ == '__main__':
    raise SystemExit(main())
