import { useCharacter, characterImage } from './character';
import { CharacterSwitch } from './Switch';
/** 登录后统一页头与每页hero；导航用当前路径标记所在页，不做任何数据读取。 */
import { Link, useLocation } from 'react-router-dom';
import { BooksIcon } from '@phosphor-icons/react';
import type { ReactNode } from 'react';

const NAV = [
  { to: '/app/library', label: '书房' },
  { to: '/app/problems', label: '我的问题' },
  { to: '/app/learning', label: '我的学习' },
  { to: '/app/bookmarks', label: '我的收藏' },
  { to: '/app/actions', label: '我的行动' },
  { to: '/app', label: '我的账号' },
];

/** 无参数；六个入口固定排序，当前页以aria-current标记。 */
export function AppHeader() {
  const { pathname } = useLocation();
  return <header className="product-header"><Link className="product-brand" to="/app"><BooksIcon size={27} aria-hidden="true" />第二大脑</Link>
    <nav aria-label="主导航">{NAV.map(item => {
      const current = pathname === item.to
        || (item.to === '/app/problems' && pathname.startsWith('/app/problems/') && !pathname.endsWith('/new'))
        || (item.to === '/app/library' && pathname.startsWith('/app/library/'));
      return <Link key={item.to} to={item.to} aria-current={current ? 'page' : undefined}>{item.label}</Link>;
    })}</nav></header>;
}

/** label/title/description为该页固定文案；pose为该页姿势素材名（自动跟随女生/男生形象）；action是页级主动作。 */
export function PageHero({ label, title, description, pose, action }: {
  label: string; title: ReactNode; description?: ReactNode; pose?: string; action?: ReactNode;
}) {
  const [character] = useCharacter();
  return <header className="page-hero">
    <span className="journal-tape tape-stripe" aria-hidden="true"></span>
    <div className="page-hero-copy">
      <p className="section-label">{label}</p>
      <h1>{title}</h1>
      {description && <p>{description}</p>}
      {action && <div className="page-hero-action">{action}</div>}
    </div>
    {pose && <div className="page-hero-side">
      <CharacterSwitch />
      <img className="page-hero-art" src={characterImage(pose, character)} alt="" aria-hidden="true" />
    </div>}
  </header>;
}
