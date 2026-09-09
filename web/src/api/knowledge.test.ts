/** 自编公开DTO检验；只替换fetch传输，不使用真实书籍或假授权结论。 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { decodeBookPage, decodeCard, decodeCardPage, decodeEvidence, decodeLibraries, readBook, readBooks, readCard, readCards, readEvidence, readLibraries } from './knowledge';

const release = '11111111-1111-4111-8111-111111111111';
const other = '22222222-2222-4222-8222-222222222222';
const version = 'a'.repeat(24);
const book = { id: 'book.自编', title: '自编方法集', author_display: '自编作者', metadata_status: 'verified' };
const source = { release_id: release, evidence_id: 'evidence.1', book, chapter: '试行', text: '先试🦉', truncated: true,
  location: { kind: 'evidence_compilation', start: 2, end: 5, paragraph_id: null, notice: '证据汇编字符位置，非原书页码' } };
const summary = { release_id: release, card_id: 'card.1', book, type: 'method', title: '有限试行', statement: '先限制损失再试行。' };
const card = { ...summary, explanation: '完整原理'.repeat(2000), conditions: ['可撤回'], boundaries: ['不可逆时不适用'], steps: ['定上限', '观察'],
  application_notes: '应用说明'.repeat(1000), source_claim_type: 'quoted_other', related: [{ id: 'relation.1', from_id: 'card.1', to_id: 'card.2', type: 'limited_by', basis: 'inference', rationale: '系统推断：受可撤回条件限制' }],
  source_previews: [source], usage_notice: '整理内容，未针对当前问题采用', gaps: [] };
const books = { release_id: release, content_version: version, items: [book], next_cursor: null };
const cards = { ...books, items: [summary] };
const libraries = { items: [{ id: release, library_id: other, title: '自编书房', description: '', content_version: version, book_count: 1, card_count: 2 }], next_cursor: null };
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe('知识公开DTO与读取边界', () => {
  it('保留完整原理、方法、原文定位与作者，仅投影公开字段', () => {
    expect(decodeCard({ ...card, prompt: 'private', book: { ...book, storage_key: 'private' } })).toEqual(card);
    expect(decodeEvidence({ ...source, file: '/private/secret' })).toEqual(source);
    expect(decodeLibraries(libraries)).toEqual(libraries);
    expect(decodeBookPage(books)).toEqual(books);
    expect(decodeCardPage(cards)).toEqual(cards);
  });
  it('未知作者保留null，空书房与无匹配列表是正常结果', () => {
    expect(decodeLibraries({ items: [], next_cursor: null }).items).toEqual([]);
    expect(decodeCardPage({ ...cards, items: [] }).items).toEqual([]);
    const unknown = { ...book, author_display: null, metadata_status: 'partial' };
    expect(decodeBookPage({ ...books, items: [unknown] }).items[0]).toEqual(unknown);
  });
  it('拒绝错误版本、跨release卡片、跨书短引及无效定位，不能误配来源', () => {
    expect(() => decodeBookPage({ ...books, content_version: 'CURRENT' })).toThrow();
    expect(() => decodeCardPage({ ...cards, items: [{ ...summary, release_id: other }] })).toThrow();
    expect(() => decodeCard({ ...card, source_previews: [{ ...source, release_id: other }] })).toThrow();
    expect(() => decodeCard({ ...card, source_previews: [{ ...source, book: { ...book, id: 'book.other' } }] })).toThrow();
    expect(() => decodeEvidence({ ...source, location: { ...source.location, end: 6 } })).toThrow();
    expect(() => decodeEvidence({ ...source, truncated: 'true' })).toThrow();
    expect(() => decodeCard({ ...card, related: [{ ...card.related[0], from_id: 'unrelated' }] })).toThrow();
  });
  it('拒绝异常分页或字段类型，不把字符串与数组转换成有效数据', () => {
    for (const bad of [null, { ...books, items: {} }, { ...books, next_cursor: 7 }, { ...books, items: [{ ...book, title: [] }] }]) expect(() => decodeBookPage(bad)).toThrow();
    expect(() => decodeLibraries({ ...libraries, items: [{ ...libraries.items[0], book_count: '1' }] })).toThrow();
    expect(() => decodeCard({ ...card, source_claim_type: 'invented' })).toThrow();
    expect(() => decodeCard({ ...card, steps: 'step' })).toThrow();
    expect(() => decodeBookPage({ ...books, items: [book, book] })).toThrow();
  });
  it('实际六个GET使用同源编码路径、查询和AbortSignal，不落盘或偷偷写入', async () => {
    const detail = { ...book, release_id: release, content_version: version, chapters: ['试行'], gaps: [] };
    const responses = [libraries, books, detail, cards, card, source];
    const fetcher = vi.fn(async () => Response.json(responses.shift()));
    vi.stubGlobal('fetch', fetcher);
    const controller = new AbortController();
    await readLibraries({ limit: 20 }, controller.signal);
    await readBooks(release, { q: '甲 & 乙', author: '自编作者' }, controller.signal);
    await readBook(release, book.id, controller.signal);
    await readCards(release, { q: '试行', book: book.id, type: 'method', cursor: 'signed:cursor', limit: 1 }, controller.signal);
    await readCard(release, card.card_id, controller.signal);
    await readEvidence(release, source.evidence_id, controller.signal);
    const paths = fetcher.mock.calls.map(call => (call as unknown[])[0] as string);
    expect(paths[0]).toBe('/api/v1/libraries?limit=20');
    expect(new URL(paths[1], 'http://localhost').searchParams.get('q')).toBe('甲 & 乙');
    expect(paths[2]).toBe(`/api/v1/libraries/${release}/books/${encodeURIComponent(book.id)}`);
    expect(new URL(paths[3], 'http://localhost').searchParams.get('cursor')).toBe('signed:cursor');
    for (const call of fetcher.mock.calls) expect((call as unknown[])[1]).toMatchObject({ method: 'GET', credentials: 'same-origin', cache: 'no-store', redirect: 'error' });
  });
  it('拒绝请求与响应ID不一致以及路径段跳转', async () => {
    const fetcher = vi.fn(async () => Response.json({ ...card, card_id: 'card.other' }));
    vi.stubGlobal('fetch', fetcher);
    await expect(readCard(release, 'card.1')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    await expect(readBook(release, '..')).rejects.toMatchObject({ code: 'INVALID_REQUEST' });
    await expect(readCards('not-a-release')).rejects.toMatchObject({ code: 'INVALID_REQUEST' });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it('知识初次校验可超过10秒，但45秒仍中止且不自动重试', async () => {
    vi.useFakeTimers();
    let aborted = false;
    const fetcher = vi.fn((_path, init) => new Promise((_resolve, reject) => init.signal.addEventListener('abort', () => { aborted = true; reject(new DOMException('abort', 'AbortError')); })));
    vi.stubGlobal('fetch', fetcher);
    const result = readBooks(release).then(() => null, error => error);
    await vi.advanceTimersByTimeAsync(10001);
    expect(aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(35000);
    expect(await result).toMatchObject({ code: 'REQUEST_TIMEOUT' });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
