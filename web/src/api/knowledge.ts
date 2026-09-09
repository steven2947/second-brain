/** 知识只读API适配；公开类型来自服务端契约，内容仅驻留当前请求/页面内存。 */
import type { components } from './generated';
import { ApiFailure, objectValue, requestJson } from './client';

export type LibraryPage = components['schemas']['LibraryPage'];
export type BookPage = components['schemas']['BookPage'];
export type CardPage = components['schemas']['CardPage'];
export type PublicBook = BookPage['items'][number];
export type Release = LibraryPage['items'][number];
export type BookDetail = components['schemas']['BookDetail'];
export type CardSummary = CardPage['items'][number];
export type BrowseCard = components['schemas']['BrowseCard'];
export type SourcePreview = components['schemas']['SourcePreview'];
export type PageQuery = { limit?: number; cursor?: string };
export type BookQuery = PageQuery & { q?: string; author?: string };
export type CardQuery = BookQuery & { book?: string; type?: string };

/** value为未知字符串；只校验类型，不人为裁掉原理或应用说明。 */
function text(value: unknown): string { if (typeof value !== 'string') throw new Error('Invalid text'); return value; }
/** value为必要的名称/ID，不能空白。 */
function nonempty(value: unknown): string { const result = text(value); if (!result.trim()) throw new Error('Empty text'); return result; }
/** value为未知数组，decode逐项投影，禁止字符串被当数组拆分。 */
function rows<T>(value: unknown, decode: (item: unknown) => T): T[] {
  if (!Array.isArray(value)) throw new Error('Invalid list');
  return value.map(decode);
}
/** value为枚举值，choices来自公开契约，不进行字符串强制转换。 */
function choice<const T extends readonly string[]>(value: unknown, choices: T): T[number] {
  if (typeof value !== 'string' || !choices.includes(value)) throw new Error('Invalid choice');
  return value as T[number];
}
/** value为计数/字符位置，min指定非负或正整数。 */
function integer(value: unknown, min = 0): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < min) throw new Error('Invalid integer');
  return value;
}
/** value为UUID；返回规范小写，避免合法大小写差异造成误配。 */
function uuid(value: unknown): string {
  const result = text(value);
  if (!/^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(result)) throw new Error('Invalid UUID');
  return result.toLowerCase();
}
/** value为已发布内容指纹前24位，不接受CURRENT等浮动别名。 */
function version(value: unknown): string { const result = text(value); if (!/^[a-f\d]{24}$/.test(result)) throw new Error('Invalid version'); return result; }
/** items为一页完整公开记录，key选择版本内唯一标识。 */
function unique<T>(items: T[], key: (item: T) => string): T[] {
  if (items.length > 100 || new Set(items.map(key)).size !== items.length) throw new Error('Invalid page');
  return items;
}
/** value为服务器签名游标，不解释、不保存到磁盘。 */
function cursor(value: unknown): string | null {
  if (value === null) return null;
  const result = nonempty(value); if (result.length > 4096) throw new Error('Invalid cursor'); return result;
}
/** value为服务端公开书目；只返回契约字段，未知作者保持null。 */
function decodeBook(value: unknown): PublicBook {
  const book = objectValue(value);
  return { id: nonempty(book.id), title: nonempty(book.title), author_display: book.author_display === null ? null : nonempty(book.author_display),
    metadata_status: choice(book.metadata_status, ['verified', 'partial']) };
}
/** value为卡片摘要，不把查询返回内容误标为本次采用。 */
function decodeSummary(value: unknown): CardSummary {
  const card = objectValue(value);
  return { release_id: uuid(card.release_id), card_id: nonempty(card.card_id), book: decodeBook(card.book),
    type: nonempty(card.type), title: nonempty(card.title), statement: nonempty(card.statement) };
}
/** value为获准知识集分页；不接受隐式计数转换或未知版本。 */
export function decodeLibraries(value: unknown): LibraryPage {
  const page = objectValue(value);
  return { items: unique(rows(page.items, value => {
    const release = objectValue(value);
    return { id: uuid(release.id), library_id: uuid(release.library_id), title: nonempty(release.title), description: text(release.description),
      content_version: version(release.content_version), book_count: integer(release.book_count, 1), card_count: integer(release.card_count, 1) };
  }), item => item.id), next_cursor: cursor(page.next_cursor) };
}
/** value为单个固定版本的书目页，不能混入重复书目。 */
export function decodeBookPage(value: unknown): BookPage {
  const page = objectValue(value);
  return { release_id: uuid(page.release_id), content_version: version(page.content_version),
    items: unique(rows(page.items, decodeBook), item => item.id), next_cursor: cursor(page.next_cursor) };
}
/** value为知识摘要页；每张卡必须属于该页声明的固定版本。 */
export function decodeCardPage(value: unknown): CardPage {
  const page = objectValue(value), release_id = uuid(page.release_id);
  const items = unique(rows(page.items, decodeSummary), item => item.card_id);
  if (items.some(item => item.release_id !== release_id)) throw new Error('Mixed release');
  return { release_id, content_version: version(page.content_version), items, next_cursor: cursor(page.next_cursor) };
}
/** value为真实短引；字符长度按Unicode码点，与Python位置规则一致。 */
export function decodeEvidence(value: unknown): SourcePreview {
  const data = objectValue(value), location = objectValue(data.location), quote = text(data.text);
  const start = integer(location.start), end = integer(location.end, 1);
  if (end <= start || end - start !== Array.from(quote).length || Array.from(quote).length > 2000 || typeof data.truncated !== 'boolean') throw new Error('Invalid source');
  return { release_id: uuid(data.release_id), evidence_id: nonempty(data.evidence_id), book: decodeBook(data.book), chapter: text(data.chapter), text: quote, truncated: data.truncated,
    location: { kind: choice(location.kind, ['original', 'evidence_compilation']), start, end,
      paragraph_id: location.paragraph_id === null ? null : nonempty(location.paragraph_id), notice: nonempty(location.notice) } };
}
/** value为整理卡详情，原理方法完整保留，来源与关系不得串版本或错接卡片。 */
export function decodeCard(value: unknown): BrowseCard {
  const data = objectValue(value), summary = decodeSummary(data);
  const sources = rows(data.source_previews, decodeEvidence);
  if (sources.some(item => item.release_id !== summary.release_id || item.book.id !== summary.book.id)) throw new Error('Mixed source');
  const related = rows(data.related, value => {
    const edge = objectValue(value);
    const result = { id: nonempty(edge.id), from_id: nonempty(edge.from_id), to_id: nonempty(edge.to_id),
      type: nonempty(edge.type), basis: choice(edge.basis, ['source', 'inference']), rationale: text(edge.rationale) };
    if (result.from_id !== summary.card_id && result.to_id !== summary.card_id) throw new Error('Unrelated card');
    return result;
  });
  return { ...summary, explanation: text(data.explanation), conditions: rows(data.conditions, text), boundaries: rows(data.boundaries, text), steps: rows(data.steps, text),
    application_notes: text(data.application_notes), source_claim_type: choice(data.source_claim_type, ['author_claim', 'quoted_other', 'system_inference', 'unknown']),
    related, source_previews: sources, usage_notice: nonempty(data.usage_notice), gaps: rows(data.gaps, text) };
}
/** value为单书详情，章节范围与缺口说明按服务端原样保留。 */
function decodeBookDetail(value: unknown): BookDetail {
  const data = objectValue(value);
  return { ...decodeBook(data), release_id: uuid(data.release_id), content_version: version(data.content_version), chapters: rows(data.chapters, text), gaps: rows(data.gaps, text) };
}
/** value为URL里的单个知识ID，拒绝路径段跳转和控制字符。 */
function segment(value: string): string {
  if (typeof value !== 'string' || !value || value === '.' || value === '..' || /[\/\\\u0000-\u001f\u007f]/.test(value)) throw new ApiFailure('INVALID_REQUEST');
  return encodeURIComponent(value);
}
/** query为页面筛选，allowed限定各端点实际支持的字段；URL编码防止查询拼接。 */
function queryString(query: PageQuery | BookQuery | CardQuery, allowed: readonly string[]): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (!allowed.includes(key)) throw new ApiFailure('INVALID_REQUEST');
    if (value === undefined || value === '') continue;
    if (key === 'limit') {
      if (typeof value !== 'number' || !Number.isInteger(value) || value < 1 || value > 100) throw new ApiFailure('INVALID_REQUEST');
    } else {
      const max = key === 'cursor' ? 4096 : key === 'q' ? 500 : key === 'type' ? 40 : 240;
      if (typeof value !== 'string' || Array.from(value).length > max) throw new ApiFailure('INVALID_REQUEST');
    }
    params.set(key, String(value));
  }
  return params.size ? '?' + params.toString() : '';
}
/** release为服务器公开UUID，suffix由内部路由生成；输入错误不发网络请求。 */
function releasePath(release: string, suffix: string): string {
  try { return `/api/v1/libraries/${uuid(release)}${suffix}`; } catch { throw new ApiFailure('INVALID_REQUEST'); }
}
/** path为本模块受控路径；knowledge首次验证较慢，45秒有界等待，不自动重试。 */
function get<T>(path: string, decoder: (value: unknown) => T, signal?: AbortSignal): Promise<T> {
  return requestJson(path, decoder, { signal, timeoutMs: 45000 });
}
/** data为解码结果，release为请求版本；响应不能混入别的知识版本。 */
function sameRelease<T extends { release_id: string }>(data: T, release: string): T {
  if (data.release_id !== uuid(release)) throw new Error('Unexpected release'); return data;
}
/** query为知识集分页；signal取消当前页面请求，不持久化数据。 */
export async function readLibraries(query: PageQuery = {}, signal?: AbortSignal): Promise<LibraryPage> {
  return get('/api/v1/libraries' + queryString(query, ['limit', 'cursor']), decodeLibraries, signal);
}
/** release为选中版本，query为书名/作者筛选，signal绑定页面生命周期。 */
export async function readBooks(release: string, query: BookQuery = {}, signal?: AbortSignal): Promise<BookPage> {
  return get(releasePath(release, '/books') + queryString(query, ['limit', 'cursor', 'q', 'author']), value => sameRelease(decodeBookPage(value), release), signal);
}
/** release/book为明确对象ID；不得接受请求外的书籍替代目标。 */
export async function readBook(release: string, book: string, signal?: AbortSignal): Promise<BookDetail> {
  return get(releasePath(release, '/books/' + segment(book)), value => { const result = sameRelease(decodeBookDetail(value), release); if (result.id !== book) throw new Error('Unexpected book'); return result; }, signal);
}
/** release为版本，query为真实卡片筛选；不给未经授权的其他版本搜索入口。 */
export async function readCards(release: string, query: CardQuery = {}, signal?: AbortSignal): Promise<CardPage> {
  return get(releasePath(release, '/cards') + queryString(query, ['limit', 'cursor', 'q', 'author', 'book', 'type']), value => sameRelease(decodeCardPage(value), release), signal);
}
/** release/card为请求目标，signal取消加载；原理完整解码而不摘要改写。 */
export async function readCard(release: string, card: string, signal?: AbortSignal): Promise<BrowseCard> {
  return get(releasePath(release, '/cards/' + segment(card)), value => { const result = sameRelease(decodeCard(value), release); if (result.card_id !== card) throw new Error('Unexpected card'); return result; }, signal);
}
/** release/evidence为所选来源；每次打开都由服务端重新检查quote权限。 */
export async function readEvidence(release: string, evidence: string, signal?: AbortSignal): Promise<SourcePreview> {
  return get(releasePath(release, '/evidence/' + segment(evidence)), value => { const result = sameRelease(decodeEvidence(value), release); if (result.evidence_id !== evidence) throw new Error('Unexpected source'); return result; }, signal);
}
