"""第二大脑本地 CLI；只读查询与显式蒸馏准备、验证、发布分开。"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from src.knowledge.library import Library, validate_library, publish_library, read_json
from src.retrieval.search import SearchEngine
from src.distillation.jobs import prepare_job, complete_job
from src.distillation.assemble import assemble_library


def _read_input(path, label):
    """读取显式 JSON 输入；拒绝目录与符号链接。"""
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"INVALID_ARGUMENT: {label} 必须是普通文件")
    return read_json(source)


def _write_json_atomic(path, document, replace=False):
    """原子写入 JSON；默认不覆盖既有目标。"""
    target = Path(path)
    parent = target.parent
    if target.is_symlink() or target.is_dir() or parent.is_symlink() or not parent.is_dir():
        raise ValueError("INVALID_ARGUMENT: 输出必须是现有普通目录中的具体文件")
    if target.exists() and not replace:
        raise ValueError("OUTPUT_EXISTS: 输出文件已存在；确认后使用 --replace")
    descriptor, temporary = tempfile.mkstemp(prefix=".call-output-", suffix=".json", dir=parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            os.replace(temporary, target)
        else:
            try:
                os.link(temporary, target)
            except FileExistsError as exc:
                raise ValueError("OUTPUT_EXISTS: 输出文件已存在；确认后使用 --replace") from exc
            Path(temporary).unlink()
        return str(target.resolve())
    finally:
        Path(temporary).unlink(missing_ok=True)


def _update_problem_file(path, event, expected_revision):
    """path 为档案路径，event 为新事件，expected_revision 为调用者所读版本；POSIX 锁防并发覆盖。"""
    import fcntl
    from src.orchestration.intake import append_event, problem_snapshot
    target = Path(path)
    if target.is_symlink() or not target.is_file() or target.parent.is_symlink():
        raise ValueError("INVALID_ARGUMENT: 档案必须是普通文件")
    # 独立锁文件保持稳定 inode，不随档案的原子替换而失效；它不存用户内容。
    lock_path = target.with_name(target.name + '.lock')
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("PROBLEM_BUSY: 另一个窗口正在更新此档案，请稍后重读") from exc
        updated = append_event(_read_input(target, '问题档案'), event, expected_revision)
        _write_json_atomic(target, updated, replace=True)
        return problem_snapshot(updated)
    finally:
        os.close(descriptor)


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
    local_import = commands.add_parser('import-local');local_import.add_argument('--book-dir',action='append',required=True);local_import.add_argument('--destination',required=True);local_import.add_argument('--allow-ready',action='store_true')
    package = commands.add_parser('package');package.add_argument('--project',default='.');package.add_argument('--destination',required=True);package.add_argument('--author-skill')
    intake_start = commands.add_parser('intake-start');intake_start.add_argument('--question',required=True)
    intake_start.add_argument('--goal',choices=['explain','analyze','compare','act','review'],default='analyze');intake_start.add_argument('--output',required=True)
    intake_update = commands.add_parser('intake-update');intake_update.add_argument('--state',required=True);intake_update.add_argument('--event',required=True);intake_update.add_argument('--expected-revision',type=int,required=True)
    intake_show = commands.add_parser('intake-show');intake_show.add_argument('--state',required=True)
    analyze = commands.add_parser('analyze');analyze.add_argument('--mode',choices=['quick','standard','deep'])
    analyze_source = analyze.add_mutually_exclusive_group(required=True)
    analyze_source.add_argument('--request');analyze_source.add_argument('--problem')
    analyze.add_argument('--previous-session',help='同一问题上一版会话；仅配合 --problem')
    analyze.add_argument('--retrieval-mode',choices=['keyword','semantic','hybrid'],default='hybrid');analyze.add_argument('--policy');analyze.add_argument('--output',required=True);analyze.add_argument('--replace',action='store_true')
    verify_analysis = commands.add_parser('validate-analysis');verify_analysis.add_argument('--session',required=True);verify_analysis.add_argument('--draft',required=True)
    verify_analysis.add_argument('--policy');verify_analysis.add_argument('--output',required=True);verify_analysis.add_argument('--replace',action='store_true')
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
        elif args.command == 'import-local':
            from src.distillation.local_markdown_adapter import import_local_books
            result = import_local_books(args.book_dir,args.destination,args.allow_ready)
        elif args.command == 'package':
            from src.interfaces.delivery import build_release
            result = build_release(args.project,args.destination,args.library,args.author_skill)
        elif args.command == 'intake-start':
            from src.orchestration.intake import create_problem, problem_snapshot
            state = create_problem(args.question,args.goal)
            path = _write_json_atomic(args.output,state)
            result = {'path':path,'snapshot':problem_snapshot(state)}
        elif args.command == 'intake-update':
            result = _update_problem_file(args.state,_read_input(args.event,'澄清事件'),args.expected_revision)
        elif args.command == 'intake-show':
            from src.orchestration.intake import problem_snapshot
            result = problem_snapshot(_read_input(args.state,'问题档案'))
        elif args.command == 'analyze':
            from src.orchestration.policy import load_policy
            from src.orchestration.session import create_call_session
            if args.previous_session and not args.problem:
                raise ValueError('INVALID_ARGUMENT: --previous-session 仅用于 --problem')
            if args.problem:
                from src.orchestration.intake import compile_request
                if args.replace:
                    raise ValueError('INVALID_ARGUMENT: 问题档案分析请使用新输出路径，保留旧会话')
                request = compile_request(
                    _read_input(args.problem,'问题档案'),
                    _read_input(args.previous_session,'上一会话') if args.previous_session else None,
                )
            else:
                request = _read_input(args.request,'调用请求')
            library = Library(args.library);version = library.version
            policy = load_policy(args.policy)
            index_root = Path(args.index_root) if args.index_root else Path(args.library).resolve().parent/'indexes'
            session = create_call_session(
                library, request, args.mode or policy['default_mode'],
                policy, args.retrieval_mode, index_root=index_root, model_cache=index_root/'model-cache'
            )
            path = _write_json_atomic(args.output,session,args.replace)
            result = {'path':path,'session_id':session['session_id'],'status':session['status'],'candidates':len(session['candidates'])}
        elif args.command == 'validate-analysis':
            from src.orchestration.policy import load_policy
            from src.orchestration.validation import build_answer_packet
            library = Library(args.library);version = library.version
            session = _read_input(args.session,'调用会话');draft = _read_input(args.draft,'分析草稿')
            packet = build_answer_packet(library,session,draft,load_policy(args.policy))
            path = _write_json_atomic(args.output,packet,args.replace)
            result = {'path':path,'session_id':packet['session_id'],'witnesses':len(packet['witness_cards']),'actions':len(packet['actions'])}
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
