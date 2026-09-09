/** 产品浏览器路由，开发连通页只在开发环境挂载。 */
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { BrowserRouter, Link, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { LoginPage } from './features/auth/LoginPage';
import { RegisterPage } from './features/auth/RegisterPage';
import { AccountPage } from './features/auth/AccountPage';
import { LibraryPage } from './features/library/LibraryPage';
import { ProblemPage } from './features/problems/ProblemPage';
import { PersonalPage } from './features/personal/PersonalPage';
import { LearningPage } from './features/learning/LearningPage';
import { AdminLoginPage, AdminPage } from './features/admin/AdminPage';
import { PrivacyPage } from './features/privacy/PrivacyPage';
import { ForgotPasswordPage, ResetPasswordPage } from './features/auth/RecoveryPage';
import './styles/auth.css';

const DevelopmentStatus = import.meta.env.DEV ? lazy(() => import('./App').then(module => ({ default: module.App }))) : null;
const DesignPreviewPage = import.meta.env.DEV ? lazy(() => import('./dev/DesignPreview').then(module => ({ default: module.DesignPreview }))) : null;
/** 无参数；未实现路由给出明确返回入口，不映射为假工作台。 */
function NotFoundPage() { return <main className="not-found"><p>第二大脑</p><h1>没有找到这一页</h1><p>地址可能有误，或这一页尚未开放。</p><Link className="link-action" to="/login">返回登录</Link></main>; }
/** 无参数；注册邮箱仅在当前React内存里移交一次，路由改变会卸载旧请求。 */
function ProductRoutes() {
  const location = useLocation(), navigate = useNavigate();
  const [registrationEmail, setRegistrationEmail] = useState('');
  const reviewDraft = useRef<{ problemId: string; prompt: string } | null>(null);
  const clearReviewDraft = useCallback(() => { reviewDraft.current = null; }, []);
  useEffect(() => {
    if (reviewDraft.current && location.pathname !== `/app/problems/${reviewDraft.current.problemId}`) clearReviewDraft();
    /** 无参数；未消费的跨页草稿也不得跨隐藏或账号切换保留。 */
    const hidden = () => { if (document.visibilityState === 'hidden') clearReviewDraft(); };
    window.addEventListener('pagehide', clearReviewDraft); document.addEventListener('visibilitychange', hidden);
    return () => { window.removeEventListener('pagehide', clearReviewDraft); document.removeEventListener('visibilitychange', hidden); };
  }, [location.pathname, clearReviewDraft]);
  /** problemId/prompt来自本人已保存行动，仅放React内存，不写URL/history或客户端存储。 */
  function review(problemId: string, prompt: string) { reviewDraft.current = { problemId, prompt }; navigate(`/app/problems/${problemId}`); }
  const clearRegistrationEmail = useCallback(() => setRegistrationEmail(''), []);
  return <Routes key={`${location.pathname}${location.search}`}>
    <Route path="/" element={<LoginPage initialEmail={registrationEmail} onEmailUsed={clearRegistrationEmail} />} />
    <Route path="/login" element={<LoginPage initialEmail={registrationEmail} onEmailUsed={clearRegistrationEmail} />} />
    <Route path="/register" element={<RegisterPage onLogin={email => { setRegistrationEmail(email); navigate('/login', { replace: true }); }} />} />
    <Route path="/forgot-password" element={<ForgotPasswordPage />} />
    <Route path="/reset-password" element={<ResetPasswordPage />} />
    <Route path="/admin/login" element={<AdminLoginPage />} />
    <Route path="/admin" element={<AdminPage />} />
    <Route path="/admin/knowledge" element={<AdminPage knowledge />} />
    <Route path="/admin/operations" element={<AdminPage operations />} />
    <Route path="/app" element={<AccountPage />} />
    <Route path="/app/settings" element={<AccountPage settings />} />
    <Route path="/app/privacy" element={<PrivacyPage />} />
    <Route path="/app/trash" element={<PrivacyPage trash />} />
    <Route path="/app/problems" element={<ProblemPage />} />
    <Route path="/app/problems/new" element={<ProblemPage />} />
    <Route path="/app/problems/:id" element={<ProblemPage reviewDraft={reviewDraft.current} onReviewUsed={clearReviewDraft} />} />
    <Route path="/app/bookmarks" element={<PersonalPage mode="bookmarks" onReview={review} />} />
    <Route path="/app/actions" element={<PersonalPage mode="actions" onReview={review} />} />
    <Route path="/app/learning" element={<LearningPage />} />
    <Route path="/app/learning/new" element={<LearningPage create />} />
    <Route path="/app/learning/:id" element={<LearningPage />} />
    <Route path="/app/library" element={<LibraryPage />} />
    <Route path="/app/library/:release/books/:book" element={<LibraryPage />} />
    <Route path="/app/library/:release/cards/:card" element={<LibraryPage />} />
    {DesignPreviewPage && <Route path="/dev/design" element={<Suspense fallback={<p role="status">正在加载设计预览…</p>}><DesignPreviewPage /></Suspense>} />}
    {DevelopmentStatus && <Route path="/dev/status" element={<Suspense fallback={<p role="status">正在读取开发状态…</p>}><DevelopmentStatus /></Suspense>} />}
    <Route path="*" element={<NotFoundPage />} />
  </Routes>;
}
/** 无参数；入口使用当前同源浏览器历史，未安装任何客户端凭据存储。 */
export function ProductApp() { return <BrowserRouter><ProductRoutes /></BrowserRouter>; }
