import { PageHero } from '../journal/Chrome';
import { AppHeader } from '../journal/Chrome';
/** 个人数据控制入口；确认身份前不读取导出或回收站，隐藏后销毁私有子树。 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { Link, useNavigate } from 'react-router-dom';
import { readMe } from '../../api/auth';
import type { DeletionReceipt } from '../../api/privacy';
import { ApiFailure } from '../../api/client';
import { knownFailure } from '../auth/shared';
import { PrivacyError, PrivacyFailure } from './shared';
import { ExportPanel } from './Exports';
import { DeletionPanel, TrashList } from './Retention';
import '../../styles/library.css';
import '../../styles/privacy.css';

/** trash选择回收站；默认展示个人导出与明确注销，不执行自动删除。 */
export function PrivacyPage({ trash = false }: { trash?: boolean }) {
  const navigate = useNavigate(), identity = useRef<AbortController | null>(null);
  const [ready, setReady] = useState(false), [failure, setFailure] = useState<ApiFailure | null>(null), [attempt, setAttempt] = useState(0), [receipt, setReceipt] = useState<DeletionReceipt | null>(null);
  const reject = useCallback((error: ApiFailure) => { if (error.code === 'AUTH_REQUIRED') { identity.current?.abort(); setReady(false); setReceipt(null); navigate('/login', { replace: true }); } }, [navigate]);
  useEffect(() => {
    let suspended = document.visibilityState === 'hidden';
    /** 无参数；恢复页面时先验证当前账号，旧请求不能带回上一身份的数据。 */
    function verify() { if (document.visibilityState === 'hidden') return; suspended = false; identity.current?.abort(); const request = new AbortController(); identity.current = request; setReady(false); setReceipt(null); setFailure(null); readMe(request.signal).then(() => { if (!request.signal.aborted) setReady(true); }).catch(error => { if (!request.signal.aborted) { const safe = knownFailure(error); setFailure(safe); reject(safe); } }); }
    /** 无参数；卸载子树时密码、确认字样、导出Blob引用和回收站记录一起释放。 */
    function hide() { suspended = true; identity.current?.abort(); flushSync(() => { setReady(false); setReceipt(null); setFailure(null); }); }
    /** 无参数；同一次恢复只读取一次身份。 */
    function restore() { if (suspended) verify(); }
    /** 无参数；隐藏与恢复均通过相同身份边界。 */
    function visibility() { if (document.visibilityState === 'hidden') hide(); else restore(); }
    if (!suspended) verify(); window.addEventListener('pagehide', hide); window.addEventListener('pageshow', restore); document.addEventListener('visibilitychange', visibility);
    return () => { identity.current?.abort(); window.removeEventListener('pagehide', hide); window.removeEventListener('pageshow', restore); document.removeEventListener('visibilitychange', visibility); };
  }, [attempt, reject]);
  /** result是服务器202回执，不表示已物理清理；立即卸载所有个人读取和表单。 */
  function accepted(result: DeletionReceipt) { identity.current?.abort(); setReady(false); setFailure(null); setReceipt(result); }
  return <div className="product-shell reading-shell"><a className="skip-link" href="#main-content">跳转到主要内容</a><AppHeader />
    <main id="main-content" className="reading-main privacy-main"><PageHero label="你的数据，由你决定" title={trash ? '问题回收站' : '隐私与数据'} description={trash ? '给删除留一段反悔的时间。恢复问题不会恢复知识授权。' : '取回个人记录，了解保存期限，或明确申请结束账号。'} />
      {receipt ? <section className="privacy-panel"><h2>注销申请已受理</h2><p>账号访问已停止，个人数据尚未立即物理删除。</p><p>冷静期截止：{new Date(receipt.purge_after).toLocaleString('zh-CN')}。到期后进入在线清理流程。</p><p>冷静期内需要取消，请联系此服务的部署负责人，通过身份核验支持流程处理；网页不提供匿名恢复入口。</p><Link to="/login">返回登录入口</Link></section>
        : failure ? <section className="reading-empty"><PrivacyError failure={failure} /><button type="button" onClick={() => setAttempt(value => value + 1)}>重新读取身份</button></section>
          : !ready ? <p role="status">正在确认登录状态…</p> : <PrivacyFailure.Provider value={reject}><nav className="privacy-tabs" aria-label="数据管理"><Link to="/app/privacy" aria-current={!trash ? 'page' : undefined}>导出与账号注销</Link><Link to="/app/trash" aria-current={trash ? 'page' : undefined}>问题回收站</Link></nav>{trash ? <TrashList /> : <><ExportPanel /><DeletionPanel onAccepted={accepted} /></>}</PrivacyFailure.Provider>}
    </main><footer className="product-footer"><span>第二大脑</span><span>不将个人问题默认用作全局训练资料。</span></footer></div>;
}
