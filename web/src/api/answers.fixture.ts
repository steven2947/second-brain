/** 纯自编契约夹具，仅用于传输与交互验证，不代表真实模型或书籍质量。 */
import type { Answer } from './answers';
export const problemId = '11111111-1111-4111-8111-111111111111', runId = '22222222-2222-4222-8222-222222222222', jobId = '33333333-3333-4333-8333-333333333333', answerId = '44444444-4444-4444-8444-444444444444';
export const answerContext = { problemId, runId, releaseId: problemId, inputRevision: 1 };
/** 无参数；为每项测试建立互不共享的完整v3答案。 */
export function answerFixture(): Answer {
  return { id: answerId, problem_id: problemId, run_id: runId, release_id: problemId, input_revision: 1, published_at: '2026-09-08T00:00:00Z', validation_status: 'structure_passed', content_hash: 'a'.repeat(64), rendered_markdown: '<script>RAW_MARKDOWN</script>', content: {
    schema_version: 3, mode: 'standard', problem: {},
    problem_framing: { confidence: 'medium', diagnostic_summary: '先明确可承受成本。', hidden_assumptions: ['结果可以观察'], key_uncertainties: ['实际投入'], reframed_question: '怎样用小规模尝试了解选择？', surface_question: '是否应该改变？' },
    books: [{ book_id: 'book.demo', title: '自编试行方法集', author_display: '自编作者甲' }],
    actions: [{ basis_card_ids: ['card.自编'], completion_criteria: '记录一次反馈', step: '先做一天小试验', stop_condition: '损失达到事先上限', validation_signal: '实际反馈可观察' }],
    argument_relations: [{ condition: '可撤回', explanation: '有限成本支持试行', from_card_ids: ['card.自编'], to_claim: '先试行', type: 'support' }],
    call_ledger: { admitted: ['card.自编'], books_searched: ['book.demo', 'book.other'], books_with_candidates: ['book.demo'], candidates: [{}], queries: ['小规模验证'], rejected: [], retrieval_degraded: false, retrieval_mode: 'keyword' },
    continuation_options: [{ basis_card_ids: ['card.自编'], description: '明确资源投入', intent: 'act', next_move: '先列出一天的成本', title: '设定试验上限' }],
    knowledge_groups: [{ card_ids: ['card.自编'], open_questions: ['何时停止？'], purpose: '组合可逆选择方法', synthesis: '先设定边界再尝试', title: '可逆试行' }],
    learning_takeaways: [{ basis_card_ids: ['card.自编'], how_to_reuse: '遇到可以撤回的选择时，先设成本界限。', method: '把决定转成试验' }],
    next_chat_action: { intent: 'act', prompt: '我愿意投入一天，请帮我明确停止条件。', reason: '下一步需要明确可承受的成本。' },
    roundtable: { support: { card_ids: ['card.自编'], claim: '支持有限试行', status: 'represented' }, opposition: { card_ids: [], claim: '未检索到充分反对证据', status: 'gap' }, alternative: { card_ids: [], claim: '可以先收集反馈', status: 'gap' }, evidence_audit: { card_ids: ['card.自编'], claim: '需要区分假设与事实', status: 'represented' } },
    sources: [{ author: '自编作者甲', book_id: 'book.demo', book_title: '自编试行方法集', card_ids: ['card.自编'], chapter: '自编第一章', evidence_id: 'e.demo', excerpt: '先限制成本，再开始尝试。', quote_available: true }],
    system_syntheses: [{ basis_card_ids: ['card.自编'], confidence: 'low', content: '可以把试验压缩为一天。', title: '一天验证方案', type: 'extension', validation_needed: '确认一天足够获得反馈' }],
    verdict: { basis_card_ids: ['card.自编'], change_conditions: ['无法撤回时改变建议'], conclusion: '先限定损失，再试行。', confidence: 'medium', consensus: ['先明确代价'], decisive_user_context_refs: [{ index: 0, kind: 'fact' }], disagreements: ['试行规模尚有分歧'], reasoning_summary: '一次小试验可以减少不确定性。', uncertainties: ['反馈能否代表长期效果'], },
    witness_cards: [{ adopted_claim: '在可撤回范围内进行小试验', assumptions: ['可以停止'], author: '自编作者甲', author_id: 'author.demo', book_id: 'book.demo', book_title: '自编试行方法集', card_id: 'card.自编', chapters: ['自编第一章'], confidence: 'medium', evidence_ids: ['e.demo'], excluded_scope: ['原卡其他论述未采用'], fit: 'partial', independent_judgment: '这一做法对可撤回选择有效', judgment_effect: '把直接投入改成限定试行', mechanism: '用有限成本换取真实反馈', misuse_risks: ['把试行当承诺'], non_applicable_conditions: ['不可逆决定'], principle: '完整原理：可撤回的试行把信息不足转为可观察反馈。'.repeat(30), principle_gap: false, quote: { evidence_id: 'e.demo', text: '先限制成本，再开始尝试。' }, roles: ['support'], situation_mapping: '对应你还不确定投入成本的处境', source_claim_type: 'quoted_other', source_gap: false, user_context_refs: [{ index: 0, kind: 'fact' }] }],
  } };
}
