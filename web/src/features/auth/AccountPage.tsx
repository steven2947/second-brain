import { characterImage, useCharacter } from '../journal/character';
import { AppHeader } from '../journal/Chrome';
/** 已登录账号入口；私有信息只驻留当前视图，每次恢复页面重新校验会话。 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { Link, useNavigate } from 'react-router-dom';
import { SignOutIcon, ArrowClockwiseIcon } from '@phosphor-icons/react';
import { logout, readMe } from '../../api/auth';
import type { PublicUser } from '../../api/auth';
import { ApiFailure } from '../../api/client';
import { ErrorNotice, knownFailure, useWriteAction } from './shared';
import { AccountSettings } from './AccountSettings';

/** settings选择账号设置；仅在真实readMe成功后显示账号和对应操作。 */
export function AccountPage({ settings = false }: { settings?: boolean }) {
  const [user, setUser] = useState<PublicUser | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const action = useWriteAction();
  const navigate = useNavigate();
  const [character] = useCharacter();
  const rejectSettings = useCallback((error: ApiFailure) => { if (error.code === 'AUTH_REQUIRED') { setUser(null); navigate('/login', { replace: true }); } }, [navigate]);
  useEffect(() => {
    /** 无参数；只接受最近一次会话读取结果。 */
    function verify() {
      controller.current?.abort();
      const request = new AbortController(); controller.current = request;
      setUser(null); setLoading(true); setFailure(null);
      readMe(request.signal).then(value => { if (!request.signal.aborted) setUser(value); })
        .catch(error => {
          if (request.signal.aborted) return;
          const safe = knownFailure(error);
          if (safe.status === 401) navigate('/login', { replace: true });
          else setFailure(safe);
        }).finally(() => { if (!request.signal.aborted) setLoading(false); });
    }
    /** 无参数；同步清空私有DOM，避免浏览器恢复缓存画面显示旧资料。 */
    function hide() {
      controller.current?.abort(); action.cancel();
      flushSync(() => { setUser(null); setLoading(true); setFailure(null); });
    }
    /** 无参数；切回标签页时必须重新读取，切走时立即遮蔽。 */
    function visibility() { if (document.visibilityState === 'hidden') hide(); else verify(); }
    verify();
    window.addEventListener('pagehide', hide); window.addEventListener('pageshow', verify);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      controller.current?.abort(); window.removeEventListener('pagehide', hide); window.removeEventListener('pageshow', verify);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [navigate, revision, action.cancel]);
  /** 无参数；退出只有服务端204确认后才导航，不把失败显示为成功。 */
  function leave() { void action.run(signal => logout(signal), () => { setUser(null); navigate('/login', { replace: true }); }); }
  return <div className="product-shell account-shell"><a className="skip-link" href="#main-content">跳转到主要内容</a>
    <AppHeader />
    <main id="main-content" className="account-content">
      {loading ? <section className="account-loading" role="status"><div className="loading-line" /><div className="loading-line short" /><p>正在确认登录状态…</p></section>
        : failure ? <section><h1>暂时无法读取账号</h1><ErrorNotice failure={failure} /><button type="button" onClick={() => setRevision(value => value + 1)}><ArrowClockwiseIcon size={18} aria-hidden="true" />重新读取账号</button></section>
          : user && (settings ? <>
            <section className="account-details" aria-label="账号资料"><dl><div><dt>邮箱</dt><dd>{user.email}</dd><dd className="verification-note">{user.email_verified_at ? '邮箱已验证' : '邮箱尚未验证'}</dd></div><div><dt>称呼</dt><dd>{user.display_name || '尚未填写'}</dd></div></dl>
              <ErrorNotice failure={action.failure} /><button className="secondary-action" type="button" onClick={leave} disabled={action.pending || action.seconds > 0}><SignOutIcon size={19} aria-hidden="true" />{action.pending ? '正在退出…' : action.seconds > 0 ? `${action.seconds} 秒后可重试` : '退出登录'}</button>
            </section>
            {settings && <AccountSettings user={user} update={setUser} reject={rejectSettings} leave={() => { setUser(null); navigate('/login', { replace: true }); }} />}
            <p className="account-back-row"><Link to="/app">返回账号首页</Link></p>
          </> : <>
            <section className="home-welcome note-card" aria-label="欢迎">
              <span className="journal-tape tape-stripe" aria-hidden="true"></span>
              <div className="home-welcome-copy"><span className="section-label">已登录 · {new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}</span>
                <h1>你好，{user.display_name || '读者'}</h1>
                <p>把真实的困惑写下来，让书里的方法帮你把问题想透。你的原话会完整保存。</p></div>
              <img className="home-welcome-reader" src={characterImage("/journal/librarian-reading", character)} alt="" aria-hidden="true" />
            </section>
            <section className="home-grid" aria-label="快捷入口">
              <Link className="home-card home-card-primary" to="/app/problems/new" aria-label="新建问题"><span className="home-card-label">从这里开始</span><strong>新建问题</strong><small>写下一个真实困惑，绑定知识集</small></Link>
              <Link className="home-card" to="/app/problems" aria-label="我的问题"><span className="home-card-label">继续上次的</span><strong>我的问题</strong><small>回到你留下的每一份思考</small></Link>
              <Link className="home-card" to="/app/library" aria-label="进入知识库"><span className="home-card-label">书架</span><strong>进入知识库</strong><small>翻阅书籍、知识卡与来源证据</small></Link>
              <Link className="home-card" to="/app/learning" aria-label="我的学习"><span className="home-card-label">练习</span><strong>我的学习</strong><small>把原理变成自己的练习</small></Link>
              <Link className="home-card" to="/app/bookmarks" aria-label="我的收藏"><span className="home-card-label">便签</span><strong>我的收藏</strong><small>留起来的知识卡与片段</small></Link>
              <Link className="home-card" to="/app/actions" aria-label="我的行动"><span className="home-card-label">行动</span><strong>我的行动</strong><small>答案里的建议，跟进到完成</small></Link>
            </section>
            <section className="account-strip" aria-label="账号资料">
              <div className="account-strip-info"><span>{user.email}</span><small>{user.email_verified_at ? '邮箱已验证' : '邮箱尚未验证'}</small><small>称呼 {user.display_name || '尚未填写'}</small></div>
              <div className="account-strip-actions"><Link className="text-action" to="/app/settings">账号设置与安全</Link>
                <ErrorNotice failure={action.failure} />
                <button className="secondary-action" type="button" onClick={leave} disabled={action.pending || action.seconds > 0}><SignOutIcon size={19} aria-hidden="true" />{action.pending ? '正在退出…' : action.seconds > 0 ? `${action.seconds} 秒后可重试` : '退出登录'}</button></div>
            </section>
            <p className="home-footer-links"><Link to="/app/privacy">隐私与数据导出</Link> · <Link to="/app/trash">问题回收站</Link> · <Link to="/forgot-password">查看密码找回方式</Link></p>
          </>)}
    </main><footer className="product-footer"><span>第二大脑</span><span>以真实来源，支持每一次思考。</span></footer>
  </div>;
}
