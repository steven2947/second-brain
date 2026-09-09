// @vitest-environment jsdom
/** 自编材料经真实组件与HTTP接缝验证阅读行为；不代替真实书籍质量验收。 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProductApp } from './ProductApp';
import type { components } from './api/generated';

const release = '11111111-1111-4111-8111-111111111111';
const other = '22222222-2222-4222-8222-222222222222';
const version = 'a'.repeat(24);
const book: components['schemas']['BookPage']['items'][number] = { id: 'sample-book', title: '林间实验笔记', author_display: null, metadata_status: 'partial' };
const libraries: components['schemas']['LibraryPage'] = { items: [release, other].map((id, i) => ({ id, library_id: id, title: i ? '另一知识集' : '自编阅读集', description: '用于验证阅读界面的自编内容', content_version: version, book_count: 1, card_count: 2 })), next_cursor: null };
const books: components['schemas']['BookPage'] = { release_id: release, content_version: version, items: [book], next_cursor: null };
const summary: components['schemas']['CardPage']['items'][number] = { release_id: release, card_id: 'sample-card', book, type: 'principle', title: '先做可撤回的实验', statement: '用小实验获得反馈。' };
const cards: components['schemas']['CardPage'] = { release_id: release, content_version: version, items: [summary], next_cursor: null };
const detail: components['schemas']['BookDetail'] = { ...book, release_id: release, content_version: version, chapters: ['第一章 小实验'], gaps: ['第二章尚无证据覆盖'] };
const source: components['schemas']['SourcePreview'] = { release_id: release, evidence_id: 'evidence-1', book, chapter: '第一章 小实验', text: '先观察一次，再决定是否重复。', truncated: true, location: { kind: 'evidence_compilation', start: 0, end: 14, paragraph_id: null, notice: '当前仅能定位到证据汇编，不代表原书页码。' } };
const card: components['schemas']['BrowseCard'] = { ...summary, explanation: '完整原理。'.repeat(160) + '原理末尾必须保留。', conditions: ['可观察结果'], boundaries: ['不适用于不可撤回的决策'], steps: ['确定一次实验', '观察反馈'], application_notes: '先明确停止条件。', source_claim_type: 'system_inference', related: [{ id: 'relation-1', from_id: 'sample-card', to_id: 'related-card', type: 'depends_on', basis: 'inference', rationale: '实验需要可观察的反馈。' }], source_previews: [source], usage_notice: '整理内容，未针对当前问题采用', gaps: ['案例覆盖有限'] };
const user: components['schemas']['PublicUser'] = { id: other, email: 'reader@example.test', display_name: '读者', theme: 'system', timezone: 'Asia/Shanghai', email_verified_at: null, created_at: '2026-09-08T00:00:00Z' };
let calls: { path: string; init?: RequestInit }[];
let respond: (path: string) => Response | Promise<Response>;
/** value/status为传输响应，自由错误文字不得被UI回显。 */
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
/** code/status为公开失败，秘密用于检测错误消息泄漏。 */
const failure = (code: string, status: number) => json({ error: { code, message: 'REMOTE SECRET TITLE', request_id: other } }, status);
/** path为真实浏览器地址。 */
function open(path = '/app/library') { window.history.replaceState(null, '', path); return render(<ProductApp />); }
/** path为请求地址，返回完整自编DTO。 */
function normal(path: string): Response {
  const url = new URL(path, 'http://localhost');
  if (url.pathname.endsWith('/me')) return json({ user });
  if (url.pathname.endsWith('/libraries')) return json(libraries);
  if (url.pathname.endsWith('/books')) return json({ ...books, release_id: url.pathname.includes(other) ? other : release });
  if (url.pathname.endsWith('/cards')) return json(cards);
  if (url.pathname.endsWith('/books/sample-book')) return json(detail);
  if (url.pathname.includes('/evidence/')) return json(source);
  return json(card);
}
beforeEach(() => { calls = []; respond = normal; vi.stubGlobal('fetch', vi.fn((path: string, init?: RequestInit) => { calls.push({ path, init }); return Promise.resolve(respond(path)); })); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('只读知识库', () => {
  it('先确认身份，匿名不请求任何知识', async () => {
    respond = () => failure('AUTH_REQUIRED', 401); open();
    await screen.findByRole('heading', { name: '欢迎回来' });
    expect(calls.every(call => call.path.endsWith('/me'))).toBe(true);
  });
  it('从账号真实链接进入书库，展示书架与完整书籍覆盖', async () => {
    open('/app'); await userEvent.click(await screen.findByRole('link', { name: '进入知识库' }));
    await userEvent.click(await screen.findByRole('link', { name: '林间实验笔记' }));
    await screen.findByText('第二章尚无证据覆盖');
    expect(screen.getByText('第一章 小实验')).toBeTruthy();
    expect(screen.getAllByText('作者信息待核实').length).toBeGreaterThan(0);
    expect(calls.some(call => call.path.includes('book=sample-book'))).toBe(true);
  });
  it('卡片详情保留原理、归属、关联方向与真实来源提示，文本不会执行HTML', async () => {
    respond = path => path.endsWith('/cards/sample-card') ? json({ ...card, title: '<img src=x onerror=alert(1)>' }) : normal(path);
    open(`/app/library/${release}/cards/sample-card`);
    await screen.findByRole('heading', { name: '<img src=x onerror=alert(1)>' });
    expect(screen.getByText(card.explanation)).toBeTruthy();
    for (const value of [...card.conditions, ...card.boundaries, ...card.steps, card.application_notes, card.usage_notice, source.text, source.location.notice]) expect(screen.getByText(value)).toBeTruthy();
    expect(screen.getAllByText(/系统推断/).length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: '查看关联知识' }).getAttribute('href')).toBe(`/app/library/${release}/cards/related-card`);
    expect(document.querySelector('img')).toBeNull();
    const refreshedText = '重新读取后的连续原文。';
    respond = () => json({ ...source, text: refreshedText, location: { ...source.location, end: Array.from(refreshedText).length } });
    await userEvent.click(screen.getByRole('button', { name: '重新读取此来源' }));
    await waitFor(() => expect(calls.some(call => call.path.endsWith('/evidence/evidence-1'))).toBe(true));
    await screen.findByText(refreshedText);
    expect(screen.queryByText(source.text)).toBeNull();
    expect(screen.getByText(card.explanation)).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });
  it('搜索显式提交，作者/书籍/类型参与过滤，翻页携带游标，改查询重置分页', async () => {
    respond = path => path.includes('/cards?') ? json({ ...cards, next_cursor: new URL(path, 'http://localhost').searchParams.has('cursor') ? null : 'signed-next' }) : normal(path);
    open(); await screen.findByRole('link', { name: book.title });
    await userEvent.click(screen.getByRole('button', { name: '知识卡片' }));
    await screen.findByRole('link', { name: summary.title });
    const before = calls.length;
    fireEvent.change(screen.getByLabelText('关键词'), { target: { value: '小实验' } });
    fireEvent.change(screen.getByLabelText('作者'), { target: { value: '作者甲' } });
    fireEvent.change(screen.getByLabelText('书籍'), { target: { value: book.id } });
    fireEvent.change(screen.getByLabelText('卡片类型'), { target: { value: 'principle' } });
    expect(calls).toHaveLength(before);
    await userEvent.click(screen.getByRole('button', { name: '搜索' }));
    await screen.findByRole('link', { name: summary.title });
    let query = new URL(calls.at(-1)!.path, 'http://localhost').searchParams;
    expect(Object.fromEntries(query)).toMatchObject({ q: '小实验', author: '作者甲', book: book.id, type: 'principle' });
    await userEvent.click(screen.getByRole('button', { name: '下一页' }));
    await screen.findByRole('link', { name: summary.title });
    expect(calls.at(-1)!.path).toContain('cursor=signed-next');
    fireEvent.change(screen.getByLabelText('关键词'), { target: { value: '新查询' } });
    await userEvent.click(screen.getByRole('button', { name: '搜索' }));
    await screen.findByRole('link', { name: summary.title });
    query = new URL(calls.at(-1)!.path, 'http://localhost').searchParams;
    expect(query.get('cursor')).toBeNull(); expect(query.get('q')).toBe('新查询');
  });
  it('切换知识集取消旧请求且清空查询，不接受延迟响应', async () => {
    let finish!: (value: Response) => void;
    respond = path => path.includes('/books?') && path.includes('q=') ? new Promise(resolve => { finish = resolve; }) : normal(path);
    open(); await screen.findByRole('link', { name: book.title });
    fireEvent.change(screen.getByLabelText('关键词'), { target: { value: 'secret-query' } });
    await userEvent.click(screen.getByRole('button', { name: '搜索' }));
    const pending = calls.at(-1)!;
    await userEvent.selectOptions(screen.getByLabelText('知识集'), other);
    await screen.findByRole('link', { name: book.title });
    expect(pending.init!.signal!.aborted).toBe(true);
    expect((screen.getByLabelText('关键词') as HTMLInputElement).value).toBe('');
    await act(async () => finish(json({ ...books, items: [{ ...book, title: '过期私有标题' }] })));
    expect(screen.queryByText('过期私有标题')).toBeNull();
  });
  it.each(['pagehide', 'hidden'])('%s同步卸载私有内容与表单，恢复先校验身份再重取', async event => {
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
    open(); await screen.findByRole('link', { name: book.title });
    fireEvent.change(screen.getByLabelText('关键词'), { target: { value: 'private input' } });
    if (event === 'hidden') { visibility.mockReturnValue('hidden'); fireEvent(document, new Event('visibilitychange')); } else fireEvent(window, new Event('pagehide'));
    expect(screen.queryByText(book.title)).toBeNull(); expect(screen.queryByDisplayValue('private input')).toBeNull();
    const count = calls.length;
    visibility.mockReturnValue('visible'); fireEvent(window, new Event('pageshow'));
    await screen.findByRole('link', { name: book.title });
    expect(calls[count].path).toBe('/api/v1/me');
    expect((screen.getByLabelText('关键词') as HTMLInputElement).value).toBe('');
    expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0);
  });
  it.each([[404, 'NOT_FOUND', '内容不存在或当前不可访问'], [503, 'RELEASE_UNAVAILABLE', '此知识版本暂时不可用']] as const)('HTTP %s清空私有内容，仅显示固定错误并允许重读', async (status, code, message) => {
    respond = path => path.endsWith('/me') ? normal(path) : failure(code, status);
    open(); await screen.findByText(message);
    expect(screen.queryByText('REMOTE SECRET TITLE')).toBeNull(); expect(screen.queryByText(libraries.items[0].title)).toBeNull();
    respond = normal; await userEvent.click(screen.getByRole('button', { name: '重新读取' }));
    await screen.findByRole('link', { name: book.title });
  });
  it('授权集合为空明确显示空状态', async () => {
    respond = path => path.endsWith('/me') ? normal(path) : json({ items: [], next_cursor: null });
    open(); await screen.findByText('暂无可访问的知识集');
    expect(screen.queryByRole('button', { name: '下一页' })).toBeNull();
  });
  it('无效参数不发知识请求', async () => {
    open('/app/library/not-a-release/cards/sample-card');
    await screen.findByText('地址参数无效');
    expect(calls.some(call => call.path.includes('/libraries'))).toBe(false);
  });
  it('书籍筛选可按真实书名选择，类型有中文含义，选择后才提交检索', async () => {
    open(); await screen.findByRole('link', { name: book.title });
    await userEvent.click(screen.getByRole('button', { name: '知识卡片' }));
    await screen.findByRole('option', { name: book.title });
    await userEvent.selectOptions(screen.getByLabelText('书籍'), book.id);
    await userEvent.selectOptions(screen.getByLabelText('卡片类型'), 'principle');
    expect(screen.getByRole('option', { name: '原理' })).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: '搜索' }));
    await screen.findByRole('link', { name: summary.title });
    expect(calls.at(-1)!.path).toContain('book=sample-book');
  });
  it('身份请求未完成不读取知识；页面卸载取消身份请求与恢复监听', async () => {
    let finish!: (value: Response) => void;
    respond = () => new Promise(resolve => { finish = resolve; });
    const view = open();
    expect(calls.map(call => call.path)).toEqual(['/api/v1/me']);
    expect(screen.getByRole('status').textContent).toContain('确认登录');
    view.unmount();
    expect(calls[0].init!.signal!.aborted).toBe(true);
    await act(async () => finish(json({ user })));
    fireEvent(window, new Event('pageshow'));
    expect(calls).toHaveLength(1);
  });
  it('来源重新读取遇到401清除整张私有卡片并回到登录', async () => {
    open(`/app/library/${release}/cards/sample-card`);
    await screen.findByText(source.text);
    respond = () => failure('AUTH_REQUIRED', 401);
    await userEvent.click(screen.getByRole('button', { name: '重新读取此来源' }));
    await screen.findByRole('heading', { name: '欢迎回来' });
    expect(screen.queryByText(card.explanation)).toBeNull(); expect(screen.queryByText(source.text)).toBeNull();
  });
  it('来源重读同证据ID却换书时清除整棵私有内容，不把其他书的文字放回原卡', async () => {
    open(`/app/library/${release}/cards/sample-card`);
    await screen.findByText(source.text);
    respond = () => json({ ...source, book: { ...book, id: 'another-book', title: '错误书籍标题' } });
    await userEvent.click(screen.getByRole('button', { name: '重新读取此来源' }));
    await screen.findByText('暂时无法读取知识内容，请稍后重试');
    expect(screen.queryByText(card.title)).toBeNull();
    expect(screen.queryByText(card.explanation)).toBeNull();
    expect(screen.queryByText(source.text)).toBeNull();
    expect(screen.queryByText(/错误书籍标题/)).toBeNull();
  });
  it('来源重读后404清除卡片标题与旧短引，隐藏时晚响应也不能回填', async () => {
    let finish!: (value: Response) => void;
    open(`/app/library/${release}/cards/sample-card`); await screen.findByText(source.text);
    respond = () => new Promise(resolve => { finish = resolve; });
    await userEvent.click(screen.getByRole('button', { name: '重新读取此来源' }));
    const request = calls.at(-1)!;
    fireEvent(window, new Event('pagehide'));
    expect(screen.queryByText(card.title)).toBeNull(); expect(request.init!.signal!.aborted).toBe(true);
    await act(async () => finish(json(source)));
    expect(screen.queryByText(source.text)).toBeNull();
    respond = normal; fireEvent(window, new Event('pageshow')); await screen.findByText(source.text);
    respond = () => failure('NOT_FOUND', 404);
    await userEvent.click(screen.getByRole('button', { name: '重新读取此来源' }));
    await screen.findByText('内容不存在或当前不可访问');
    expect(screen.queryByText(card.title)).toBeNull(); expect(screen.queryByText(source.text)).toBeNull();
  });
  it('知识集分页和书籍选项更多仅显式读取签名游标', async () => {
    respond = path => {
      const url = new URL(path, 'http://localhost');
      if (url.pathname.endsWith('/libraries')) return json({ items: [libraries.items[url.searchParams.has('cursor') ? 1 : 0]], next_cursor: url.searchParams.has('cursor') ? null : 'release-next' });
      if (url.pathname === `/api/v1/libraries/${other}/books`) return json({ ...books, release_id: other, items: [{ ...book, id: 'second-release-book', title: '第二知识集书籍' }], next_cursor: null });
      if (url.pathname.endsWith('/books')) return json({ ...books, items: url.searchParams.has('cursor') ? [{ ...book, id: 'another-book', title: '另一自编书' }] : [book], next_cursor: url.searchParams.has('cursor') ? null : 'books-next' });
      return normal(path);
    };
    open(); await screen.findByRole('link', { name: book.title });
    await userEvent.click(screen.getByRole('button', { name: '知识卡片' }));
    await screen.findByRole('option', { name: book.title });
    expect(calls.some(call => call.path.includes('cursor=books-next'))).toBe(false);
    await userEvent.click(screen.getByRole('button', { name: '更多书籍' }));
    await screen.findByRole('option', { name: '另一自编书' });
    expect(screen.getByRole('option', { name: book.title })).toBeTruthy();
    expect(calls.some(call => call.path.includes('cursor=books-next'))).toBe(true);
    // 卡片无下一页，此处唯一下一页属于获准知识集列表。
    await userEvent.click(screen.getByRole('button', { name: '下一页' }));
    await waitFor(() => expect(calls.some(call => call.path.includes('cursor=release-next'))).toBe(true));
    const nextBook = await screen.findByRole('link', { name: '第二知识集书籍' });
    expect(nextBook.getAttribute('href')).toBe(`/app/library/${other}/books/second-release-book`);
    expect((screen.getByLabelText('知识集') as HTMLSelectElement).value).toBe(other);
    expect(screen.queryByRole('alert')).toBeNull();
  });
  it('空卡片列表如实提示，没有可翻页的假操作', async () => {
    respond = path => path.includes('/cards?') ? json({ ...cards, items: [] }) : normal(path);
    open(`/app/library/${release}/books/sample-book`);
    await screen.findByText('没有符合条件的知识卡片，可以调整筛选条件。');
    expect(screen.queryByRole('button', { name: '下一页' })).toBeNull();
  });
  it('书目列表显示切换不重复请求，翻页保留过滤并可回上一页', async () => {
    respond = path => path.includes('/books?') ? json({ ...books, next_cursor: new URL(path, 'http://localhost').searchParams.has('cursor') ? null : 'books-next' }) : normal(path);
    open(); await screen.findByRole('link', { name: book.title });
    const count = calls.length;
    await userEvent.click(screen.getByRole('button', { name: '列表' }));
    expect(calls).toHaveLength(count); expect(document.querySelector('.text-cover')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: '下一页' }));
    await screen.findByRole('link', { name: book.title }); expect(calls.at(-1)!.path).toContain('cursor=books-next');
    await userEvent.click(screen.getByRole('button', { name: '上一页' }));
    await screen.findByRole('link', { name: book.title }); expect(calls.at(-1)!.path).not.toContain('cursor=');
  });
  it('已有作者字段不冒充做过书目事实审核', async () => {
    respond = path => path.includes('/books?') ? json({ ...books, items: [{ ...book, author_display: '自编作者', metadata_status: 'verified' }] }) : normal(path);
    open(); await screen.findByRole('link', { name: book.title });
    expect(screen.queryByText('书目信息已核实')).toBeNull();
  });
});
