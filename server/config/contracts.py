"""产品公开API的唯一合并出口；账号与知识模块各自持有实际字段事实源。"""
import json
from accounts.contracts import build_contract as account_contract
from knowledge.contracts import build_fragment as knowledge_fragment
from problems.contracts import build_fragment as problem_fragment
from runs.contracts import build_fragment as run_fragment
from answers.contracts import build_fragment as answer_fragment
from personal.contracts import build_fragment as personal_fragment
from learning.contracts import build_fragment as learning_fragment
from administration.contracts import build_fragment as administration_fragment
from publishing.contracts import build_fragment as publishing_fragment
from operations.contracts import build_fragment as privacy_fragment


def build_contract():
    """无参数；保留全部账号操作，合并实际知识与问题片段，冲突时停止生成。"""
    contract = account_contract()
    for fragment in (knowledge_fragment, problem_fragment, run_fragment, answer_fragment, personal_fragment, learning_fragment, administration_fragment, publishing_fragment, privacy_fragment):
        paths, schemas = fragment()
        if set(paths) & set(contract['paths']) or set(schemas) & set(contract['components']['schemas']):
            raise ValueError('产品契约名称冲突')
        contract['paths'].update(paths)
        contract['components']['schemas'].update(schemas)
    contract['info'].update(title='第二大脑产品接口', version='0.12.0',
        description='实际账号、知识、问题、消息、任务、正式答案、收藏、行动、反馈、独立学习、管理员多因素身份、受控知识发布授权与账号额度及本机邀请运营接口；真实模型效果仍需单独验收。')
    return contract


def contract_text():
    """无参数；稳定排序输出，供生成类型与只读漂移检查。"""
    return json.dumps(build_contract(), ensure_ascii=False, sort_keys=True, indent=2) + '\n'
