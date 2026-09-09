import { CharacterSwitch } from '../features/journal/Switch';
/** 仅开发环境的设计预览：fixture数据与静态对话样张，不读取账号、问题或答案，不发起任何API请求。 */
import { BooksIcon } from '@phosphor-icons/react';
import { answerFixture } from '../api/answers.fixture';
import { AnswerBody } from '../features/answers/AnswerView';
import type { Run } from '../api/runs';

const stageOrder: Extract<Run['stage'], string>[] = ['understanding', 'retrieving', 'evaluating', 'validating', 'composing'];
const stageLabels: Record<Run['stage'], string> = { accepted: '已接收', understanding: '理解问题', retrieving: '检索知识', evaluating: '评估观点', validating: '核验证据', composing: '组织表达' };

/** 无参数；纯静态样张，生产构建不注册此路由。 */
export function DesignPreview() {
  const answer = answerFixture();
  return <main className="product-shell reading-shell problem-shell">
    <header className="product-header"><LinkLike /></header>
    <div className="reading-main" style={{ maxWidth: 900, margin: '0 auto' }}>
      <div className="reading-heading"><p className="section-label">设计预览 · fixture数据</p><h1>手帐书房 · 样张</h1><p>仅开发环境可见。以下按钮均为样式摆件、不可点击（除右上角形象切换）；真实交互请到正式页面。</p>
      <CharacterSwitch /></div>

      <section className="chat-section" aria-label="对话样张">
        <div className="chat-heading"><div><p className="section-label">把思考继续下去</p><h2>对话记录</h2></div><span className="reading-muted">你的原话会完整保存</span></div>
        <ol className="chat-messages">
          <li className="chat-message chat-message-user"><span className="chat-speaker">你</span><p>我下班后总想刷手机，学习计划总是坚持不过三天。怎么建立可持续的学习习惯？</p></li>
          <li className="chat-message chat-message-assistant chat-message-clarification"><span className="chat-speaker">AI</span><p>Q1：之前的学习计划，通常在哪个环节中断？是启动太难、任务太大，还是缺少反馈？</p></li>
          <li className="chat-message chat-message-user"><span className="chat-speaker">你</span><p>主要败在任务太大，一小时里经常贪多；打卡群只有记录没有反馈。</p></li>
          <li className="chat-message chat-message-assistant"><span className="chat-speaker">AI</span><p>明白了。你更喜欢「每天一个小产出」的方式，我会把这一点纳入分析。</p></li>
        </ol>
        <section className="chat-task" aria-label="任务样张">
          <span className="journal-tape tape-stripe" aria-hidden="true"></span>
          <p className="chat-task-label">本次提交关联的任务</p>
          <div className="chat-task-line"><strong>处理中</strong><span>评估观点 · 输入修订 3</span></div>
          <ul className="chat-stages" aria-hidden="true">
            {stageOrder.map((stage, index) => <li key={stage} className={index < 2 ? 'stage-done' : index === 2 ? 'stage-now' : ''}>{stageLabels[stage]}</li>)}
          </ul>
          <p>任务正在进行中，完成后这里会出现正式答案。</p>
          <img className="chat-task-reader" src="/journal/librarian-magnify.png" alt="" aria-hidden="true" />
        </section>
        <div className="chat-compose">
          <div className="reading-field"><label htmlFor="preview-draft">补充背景或回应追问</label><textarea id="preview-draft" rows={3} placeholder="你现在最在意什么？也可以写下新的事实……" readOnly /></div>
          <div className="chat-controls"><div className="reading-field"><label htmlFor="preview-intent">这条消息的用途</label><select id="preview-intent" disabled><option>补充背景</option></select></div><div className="problem-actions"><button type="button" disabled>发送消息</button><button className="secondary-action" type="button" disabled>直接分析</button></div></div>
        </div>
      </section>

      <AnswerBody answer={answer} onContinue={() => {}} disabled={false} />
    </div>
  </main>;
}

function LinkLike() {
  return <span className="product-brand"><BooksIcon size={27} aria-hidden="true" />第二大脑</span>;
}
