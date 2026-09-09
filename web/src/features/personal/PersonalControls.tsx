/** 书卡和答案内的明确写入动作；不自动生成学习评语或启动模型。 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { BookmarkSimpleIcon, CheckIcon } from '@phosphor-icons/react';
import { createAction, saveBookmark, sendFeedback } from '../../api/personal';
import type { Feedback } from '../../api/personal';
import type { ApiFailure } from '../../api/client';
import { useWriteAction } from '../auth/shared';
import '../../styles/personal.css';

export const feedbackLabels = { helpful: '有帮助', shallow: '建议还不够深入', unclear_principle: '原理讲得不清楚', wrong_source: '来源可能有误', other: '其他意见' };
/** failure为固定错误，绝不回显服务端自由文本。 */
export function PersonalError({ failure }: { failure: ApiFailure | null }) {
  return failure ? <p role="alert">{failure.status === 409 ? '记录已在其他地方更新。你的输入仍保留，请重新读取后核对。' : failure.status === 429 ? '请求较多，请等待后再试。' : '暂时无法确认保存结果，请稍后重试。'}</p> : null;
}
/** release/card来自正在阅读的真实卡片；不传备注可保留已有收藏笔记。 */
export function BookmarkControl({ release, card, onFailure }: { release: string; card: string; onFailure: (error: ApiFailure) => void }) {
  const action = useWriteAction(), [saved, setSaved] = useState(false);
  return <div className="personal-inline"><button className="secondary-action" type="button" disabled={saved || action.pending || action.seconds > 0}
    onClick={() => void action.run(signal => saveBookmark(release, card, undefined, signal), () => setSaved(true), error => { if (error.status === 401 || error.status === 404) onFailure(error); })}>
    {saved ? <CheckIcon size={18} aria-hidden="true" /> : <BookmarkSimpleIcon size={18} aria-hidden="true" />}{saved ? '已收藏' : action.pending ? '正在收藏…' : '收藏这张知识卡'}</button><Link to="/app/bookmarks">查看我的收藏</Link><PersonalError failure={action.failure} /></div>;
}
/** answer/index仅引用正式答案；重复加入由服务端返回同一记录，不覆盖已执行状态。 */
export function SaveActionControl({ answer, index, disabled, onFailure }: { answer: string; index: number; disabled: boolean; onFailure: (error: ApiFailure) => void }) {
  const write = useWriteAction(), [saved, setSaved] = useState(false);
  return <div className="personal-inline"><button className="secondary-action" type="button" disabled={disabled || saved || write.pending || write.seconds > 0}
    onClick={() => void write.run(signal => createAction(answer, index, signal), () => setSaved(true), error => { if (error.status === 401 || error.status === 404) onFailure(error); })}>{saved ? '已加入行动记录' : write.pending ? '正在保存…' : '加入我的行动'}</button>{saved && <Link to="/app/actions">记录执行与反馈</Link>}<PersonalError failure={write.failure} /></div>;
}
/** answer为当前正式答案ID；反馈仅保存明确意见，不自动继续分析。 */
export function AnswerFeedback({ answer, onFailure }: { answer: string; onFailure: (error: ApiFailure) => void }) {
  const write = useWriteAction(), [category, setCategory] = useState<Feedback['category']>('helpful'), [comment, setComment] = useState(''), [sent, setSent] = useState(false);
  return <details className="personal-feedback"><summary>这次分析对你有帮助吗？</summary>{sent ? <p role="status">意见已保存，谢谢你帮助我们改进分析质量。</p> : <form onSubmit={event => { event.preventDefault(); void write.run(signal => sendFeedback({ answer_id: answer, category, comment }, signal), () => { setSent(true); setComment(''); }, error => { if (error.status === 401 || error.status === 404) onFailure(error); }); }}>
    <label>你更想反馈什么<select value={category} onChange={event => setCategory(event.target.value as Feedback['category'])}>{Object.entries(feedbackLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <label>具体说明（可选）<textarea value={comment} maxLength={2000} rows={3} onChange={event => setComment(event.target.value)} placeholder="哪条建议、原理或来源值得调整？" /></label><PersonalError failure={write.failure} /><button type="submit" disabled={write.pending || write.seconds > 0}>{write.pending ? '正在保存…' : '提交这次反馈'}</button>
  </form>}</details>;
}
