"""真实消息任务端点的OpenAPI片段；不预告尚未存在的SSE/答案接口。"""
from uuid import UUID
from django.urls import resolve, reverse
from rest_framework import serializers
from accounts.contracts import reference
from knowledge.contracts import public_field_schema, public_serializer_schema

OPERATIONS = (
    ('problem-messages','GET','listMessages','problem_id',200),
    ('problem-messages','POST','sendMessage','problem_id',202),
    ('problem-analyze','POST','startAnalysis','problem_id',202),
    ('run-detail','GET','getRun','run_id',200),
    ('job-detail','GET','getJob','job_id',200),
    ('job-cancel','POST','cancelJob','job_id',202),
)


def build_fragment():
    """无参数；从已注册views读取输入/输出字段，不建立第二套DTO。"""
    paths, schemas = {}, {}
    for route, method, operation_id, parameter, status in OPERATIONS:
        identifier = UUID(int=1)
        url = reverse(route, kwargs={parameter: identifier})
        view = resolve(url).func
        if method not in view.allowed_methods:
            raise ValueError('任务契约引用未实现的方法')
        url = url.replace(str(identifier), '{'+parameter+'}')
        parameters = [{'name': parameter,'in':'path','required':True,
                       'schema':{'type':'string','format':'uuid'}}]
        response = view.response_serializers[method]
        name = response.__name__.removesuffix('Serializer')
        schemas[name] = public_serializer_schema(response())
        operation = {'operationId':operation_id,'security':[{'SessionCookie':[]}],
            'parameters':parameters,'responses':{
                str(status):{'description':'真实任务或本人消息；禁止缓存',
                    'content':{'application/json':{'schema':reference(name)}}},
                'default':{'description':'固定公开错误',
                    'content':{'application/json':{'schema':reference('ErrorResponse')}}}}}
        if method == 'GET':
            for key, field in view.query_serializer().fields.items():
                schema = public_field_schema(field)
                if field.default is not serializers.empty:
                    schema['default'] = field.default
                parameters.append({'name':key,'in':'query','required':field.required,'schema':schema})
        else:
            parameters.append({'$ref':'#/components/parameters/CsrfHeader'})
            input_name = 'CancelJobInput' if route == 'job-cancel' else view.input_serializer.__name__.removesuffix('Serializer')
            schemas[input_name] = public_serializer_schema(view.input_serializer())
            operation['requestBody'] = {'required': route != 'job-cancel',
                'content':{'application/json':{'schema':reference(input_name)}}}
            if route == 'job-cancel':
                operation['responses']['200'] = operation['responses']['202']
            else:
                parameters.append({'name':'Idempotency-Key','in':'header','required':True,
                    'schema':{'type':'string','minLength':1,'maxLength':128}})
                operation['responses']['409'] = {'description':'修订或幂等冲突',
                    'content':{'application/json':{'schema':{'oneOf':[
                        reference('ProblemConflictResponse'),reference('ErrorResponse')]}}}}
        paths.setdefault(url,{})[method.lower()] = operation
    return paths, schemas
