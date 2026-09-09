# 十本书蒸馏与多书候选库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 复用现有蒸馏脚本、仓颉 Skill 和项目提示词，完成 10 本新增书籍的可追踪批次管理、逐书验收和多书候选库合并能力。

**Architecture:** 原书仍由 `configs/local.json` 只读引用；每本书继续使用现有 `prepare/assemble/complete/validate` 单书流程和 `vendor/cangjie/SKILL.md`。新增部分仅负责十书计划校验、已验证单书候选的纯文件合并、CLI 暴露和多书验收记录，不重新实现正文蒸馏、卡片提取、仓颉编译或问答 Skill。

**Tech Stack:** Python 3.12；现有 `src/distillation`、`src/knowledge.library`、`src.interfaces.cli`；JSON/JSON Schema；项目已有 unittest、PyYAML、jsonschema 和仓颉 v2.5.0 工作副本。

**Spec:** [十本新增书籍蒸馏与多书知识库设计](../specs/2026-09-09-ten-book-distillation-design.md)

## Global Constraints

- 原书路径由 `configs/local.json.source_books_root` 解析，只读访问；不得修改、复制、移动或上传 `data/originals/` 指向的外部原书。
- 不新增蒸馏算法、模型调度器、提示词套件或 Skill；复用 `tools/dev/inventory_books.py`、`src.interfaces.cli prepare/assemble/complete/validate/publish`、`prompts/distillation/`、`vendor/cangjie/SKILL.md` 和 `skills/second-brain/SKILL.md`。
- 自定义代码只放 `src/`、`tools/dev/` 或测试；不得修改 `vendor/cangjie/`。
- `data/jobs/`、`data/normalized/`、真实候选库、索引和模型缓存是运行数据，不提交；计划清单不能包含绝对路径、凭据或源文件内容。
- 规范化正文和原文映射是事实源；知识卡、关系、证据汇编、索引和答案包都是派生物。结构验证不能替代语义复核。
- 每本书必须独立通过范围、完整覆盖、证据结构和语义抽样门禁；失败书籍不得进入多书候选。
- 不在本计划执行正式 `publish`，除非用户在候选验收后再次明确授权；任何候选失败都必须保留当前 `CURRENT`。
- 每个新增函数都写中文用途说明和参数说明；领域规则不能依赖 CLI、HTML、浏览器或 Agent 会话状态。

## File Map

- Create `configs/ten-book-distillation-plan.json`: 十本书的稳定清单、波次、相对来源路径和状态；不含本机绝对路径。
- Create `schemas/distillation-batch-plan.schema.json`: 计划清单的结构契约。
- Create `src/distillation/batch_plan.py`: 计划清单的纯规则校验和来源路径检查。
- Create `tools/dev/validate_distillation_plan.py`: 调用现有路径配置的只读 CLI 包装。
- Create `src/distillation/merge.py`: 合并已验证单书候选的纯文件实现；不读取原书、不调用模型。
- Create `tests/test_batch_plan.py`: 清单和来源检查测试。
- Create `tests/test_multibook_merge.py`: 多书合并、来源隔离、ID 冲突和失败回退测试。
- Modify `src/interfaces/cli.py`: 增加 `merge-candidates` 命令，不改变已有命令。
- Modify `tests/test_orchestration_cli.py`: 验证新 CLI 输出和错误契约，同时覆盖已有 `books` 命令不回归。
- Modify `src/interfaces/README.md`: 记录新命令和职责边界。
- Modify `docs/distillation-workflow.md`: 记录十书批次执行和候选合并命令。
- Modify `docs/architecture.md`: 将多书候选合并从“未实现”更新为已实现能力，并保留跨书语义综合未实现的边界。
- Modify `docs/README.md`: 链接本计划和后续真实执行记录。
- Runtime-only under ignored `data/jobs/ten-books/`: 每本书的 scope、prepare 任务、Agent 输出、单书验收、检索题集和波次回执。

### Task 1: 建立十书计划清单与只读校验

**Files:**
- Create: `configs/ten-book-distillation-plan.json`
- Create: `schemas/distillation-batch-plan.schema.json`
- Create: `src/distillation/batch_plan.py`
- Create: `tools/dev/validate_distillation_plan.py`
- Test: `tests/test_batch_plan.py`

**Interfaces:**
- `load_batch_plan(path: str | Path) -> dict`: 读取并校验计划 JSON，`path` 为计划文件。
- `validate_batch_plan(plan: dict, source_root: str | Path | None = None, check_sources: bool = False, wave: int | None = None) -> dict`: 校验十本书的稳定 ID、波次、相对路径、状态和可选来源存在性；`source_root` 为只读原书根目录，`check_sources` 控制是否检查真实文件，`wave` 可限制检查某一波次。
- `validate_distillation_plan.py --plan <plan-path> [--source-root <source-root>] [--check-sources] [--wave 1|2]`: 输出 JSON 结果；来源检查失败返回非零退出码。

计划文件必须包含以下 10 条，不得自行替换书目：

```json
[
  [1, 1, "book.card-notes-writing", "卡片笔记写作法", "剩余126本/01_认知与思维/卡片笔记写作法/卡片笔记写作法.md"],
  [2, 1, "book.asking-the-right-questions", "学会提问", "首批42本/学会提问/学会提问.md"],
  [3, 1, "book.peak-practice", "刻意练习", "剩余126本/02_学习方法与个人成长/刻意练习/刻意练习.md"],
  [4, 1, "book.zero-to-one", "从0到1", "剩余126本/06_创业与商业/从0到1/从0到1.md"],
  [5, 1, "book.positioning", "定位", "剩余126本/07_营销与增长/定位/定位.md"],
  [6, 2, "book.poor-charlie-almanack", "穷查理宝典", "剩余126本/01_认知与思维/穷查理宝典/穷查理宝典.md"],
  [7, 2, "book.principles", "原则", "剩余126本/01_认知与思维/原则/原则.md"],
  [8, 2, "book.scarcity", "稀缺", "剩余126本/01_认知与思维/稀缺/稀缺.md"],
  [9, 2, "book.index-fund-investing", "指数基金投资指南", "剩余126本/04_投资经典/指数基金投资指南/指数基金投资指南.md"],
  [10, 2, "book.economic-way-of-thinking", "经济学的思维方式", "首批42本/经济学的思维方式/经济学的思维方式.md"]
]
```

- [ ] **Step 1: Write failing tests for plan shape and source safety.**

  In `tests/test_batch_plan.py`, create a temporary source root and assert:

  ```python
  def test_approved_plan_has_ten_unique_books_in_two_waves():
      result = validate_batch_plan(load_batch_plan(PLAN), wave=None)
      self.assertEqual(result["books"], 10)
      self.assertEqual(result["waves"], {"1": 5, "2": 5})

  def test_source_check_accepts_relative_files_and_rejects_absolute_escape():
      result = validate_batch_plan(plan, source_root=temp_root, check_sources=True)
      self.assertEqual(result["source_paths_checked"], 10)
      plan["books"][0]["source_relative_path"] = "../outside.md"
      with self.assertRaisesRegex(ValueError, "SOURCE_PATH"):
          validate_batch_plan(plan, source_root=temp_root, check_sources=True)

  def test_duplicate_book_id_and_invalid_wave_are_rejected():
      plan["books"][1]["book_id"] = plan["books"][0]["book_id"]
      with self.assertRaisesRegex(ValueError, "BOOK_ID"):
          validate_batch_plan(plan)
  ```

- [ ] **Step 2: Run the focused test to confirm it fails.**

  Run: `.venv-mvp/bin/python -m unittest tests.test_batch_plan -v`

  Expected: FAIL because the plan validator module and committed plan do not exist.

- [ ] **Step 3: Add the schema, literal ten-book plan, and pure validator.**

  The schema must require `schema_version: 1`, `plan_id`, `books`, and `waves`; require exactly 10 book entries; constrain each `book_id` to `book.[a-z0-9-]+`, `wave` to 1 or 2, `status` to `planned|prepared|distilled|accepted|blocked`, and source paths to relative strings. The Python validator must additionally reject absolute paths, `..` path escapes, duplicate IDs, duplicate orders, wrong wave counts, and non-unique source paths. It must only read files when `check_sources=True`.

- [ ] **Step 4: Add the read-only CLI wrapper.**

  `tools/dev/validate_distillation_plan.py` must resolve `--source-root` through `project_paths.load_local_config()` when omitted, call `validate_batch_plan`, print JSON, and return 1 on `OSError` or `ValueError`. It must not create `data/jobs`, rewrite the plan, or calculate book status from file existence alone.

- [ ] **Step 5: Run the focused tests and the real local-source check.**

  Run:

  ```bash
  .venv-mvp/bin/python -m unittest tests.test_batch_plan -v
  .venv-mvp/bin/python tools/dev/validate_distillation_plan.py \
    --plan configs/ten-book-distillation-plan.json --check-sources
  ```

  Expected: all focused tests pass and the CLI reports 10 checked source paths with 5 books in each wave.

- [ ] **Step 6: Commit the batch registry and validator.**

  ```bash
  git add configs/ten-book-distillation-plan.json schemas/distillation-batch-plan.schema.json \
    src/distillation/batch_plan.py tools/dev/validate_distillation_plan.py tests/test_batch_plan.py
  git commit -m "feat: 增加十书蒸馏批次清单校验"
  ```

### Task 2: 实现已验证单书候选的多书合并器

**Files:**
- Create: `src/distillation/merge.py`
- Test: `tests/test_multibook_merge.py`

**Interfaces:**
- `merge_libraries(candidates: list[str | Path], destination: str | Path, library_id: str, release_status: str = "evaluation_candidate") -> dict`: 合并已通过 `validate_library` 的单书候选；`candidates` 顺序决定 manifest、关系和候选目录中的稳定顺序，`destination` 必须不存在，`library_id` 使用 `library.[a-z0-9-]+`，`release_status` 只能是 `evaluation_candidate` 或 `accepted_candidate`。
- 返回值至少包含 `path`、`library_id`、`release_status`、`books`、`cards`、`evidence`、`relations` 和 `source_candidates`。

实现约束：复用 `validate_library`、`load_records`、`read_json`、`write_json` 和 `content_version`；不把合并器放入 `knowledge.library`，因为它是候选装配职责，不是查询规则；不读取原书，不修改输入候选。

- [ ] **Step 1: Write failing merge tests using copied sample libraries.**

  In `tests/test_multibook_merge.py`, copy `examples/sample-library/` into two temporary candidate directories and rewrite the second fixture through a test-only helper so its book, card, evidence, source paragraph and relation IDs are distinct. Add tests for:

  ```python
  def test_merge_preserves_books_and_isolates_evidence_sources():
      result = merge_libraries([first, second], destination, "library.two-book-test")
      report = validate_library(destination)
      self.assertEqual(report["books"], 2)
      self.assertEqual(Library(destination).list_books().__len__(), 2)
      evidence = load_records(destination / "evidence")
      self.assertEqual(len({item["source_path"] for item in evidence.values()}), 2)
      self.assertTrue(all(item["source_path"].startswith("sources/candidate-") for item in evidence.values()))

  def test_duplicate_book_or_card_id_is_rejected_without_destination():
      with self.assertRaisesRegex(ValueError, "DUPLICATE"):
          merge_libraries([first, first], destination, "library.duplicate-test")
      self.assertFalse(destination.exists())

  def test_invalid_candidate_and_existing_destination_are_rejected():
      (first / "sources/demo.md").write_text("损坏", encoding="utf-8")
      with self.assertRaises(ValueError):
          merge_libraries([first, second], destination, "library.invalid-test")
      self.assertFalse(destination.exists())
  ```

- [ ] **Step 2: Run the focused merge tests to confirm they fail.**

  Run: `.venv-mvp/bin/python -m unittest tests.test_multibook_merge -v`

  Expected: FAIL because `src.distillation.merge` does not exist.

- [ ] **Step 3: Implement deterministic, atomic merge.**

  Validate every input first. Reject an empty list, missing candidate, invalid release status, invalid library ID, duplicate book/card/evidence/relation ID, missing source directory, existing destination, or non-directory destination parent. Create a temporary directory beside `destination`; copy each candidate's `sources/` to `sources/candidate-000/`, `sources/candidate-001/`, and so on; rewrite each copied evidence record's relative `source_path` while preserving its original `source_sha256` and `origin` mapping. Write cards at top level with a deterministic book prefix to avoid filename collisions, write evidence the same way, concatenate relation edges in candidate order, and copy each per-book `coverage.json` to `coverage/<book_id>.json`.

  Construct a manifest with all input books, `library_id`, `distillation_mode: "multi_book_candidate"`, `release_status`, `cards_directory`, `evidence_directory`, `relations_file`, and `coverage_directory`. Do not add cross-book edges. Run `validate_library` on the temporary output, then atomically rename it to `destination`; on every exception remove only the temporary directory.

- [ ] **Step 4: Run focused tests and verify deterministic output.**

  Run:

  ```bash
  .venv-mvp/bin/python -m unittest tests.test_multibook_merge -v
  .venv-mvp/bin/python -m unittest tests.test_library -v
  ```

  Expected: merge tests and existing library publication tests pass; repeated merges from the same ordered candidates produce the same `content_version`.

- [ ] **Step 5: Commit the merge core.**

  ```bash
  git add src/distillation/merge.py tests/test_multibook_merge.py
  git commit -m "feat: 合并已验证的多书候选库"
  ```

### Task 3: 暴露 `merge-candidates` CLI 并保留现有命令契约

**Files:**
- Modify: `src/interfaces/cli.py`
- Modify: `tests/test_orchestration_cli.py`
- Modify: `src/interfaces/README.md`

**Interfaces:**
- CLI: `python -m src.interfaces.cli merge-candidates --candidate <candidate-dir> --candidate <candidate-dir> --destination <destination-dir> --library-id <library-id> [--release-status evaluation_candidate|accepted_candidate]`；重复的 `--candidate` 顺序就是合并顺序。
- 输出继续使用现有包装：`schema_version: 1`、`library_version: null`、`result`；错误继续返回 JSON stderr 和退出码 2。

- [ ] **Step 1: Add failing CLI tests.**

  Extend `tests/test_orchestration_cli.py` with a test that passes two copied sample candidates, asserts status 0, asserts `result.path`, and opens the destination with `Library`. Add a second test with a duplicate candidate and assert status 2 plus `DUPLICATE` in stderr. Keep the existing `books` compatibility assertion unchanged.

- [ ] **Step 2: Run the focused CLI tests to confirm the new command fails.**

  Run: `.venv-mvp/bin/python -m unittest tests.test_orchestration_cli -v`

  Expected: the new merge test fails because the parser does not know `merge-candidates`.

- [ ] **Step 3: Add the parser branch without moving domain logic into CLI.**

  Add an `argparse` subparser with repeatable required `--candidate`, required `--destination`, required `--library-id`, and the two allowed `--release-status` choices. Import `merge_libraries` at module scope alongside `prepare_job` and `assemble_library`, dispatch before the generic `Library(args.library)` query branch, and leave `args.library` unused for this command. Return the merge result through the existing JSON wrapper.

- [ ] **Step 4: Run CLI and regression tests.**

  Run:

  ```bash
  .venv-mvp/bin/python -m unittest tests.test_orchestration_cli -v
  .venv-mvp/bin/python -m src.interfaces.cli --help
  ```

  Expected: all CLI tests pass and help lists `merge-candidates`; existing commands remain unchanged.

- [ ] **Step 5: Document the command boundary and commit.**

  Update `src/interfaces/README.md` to say that `merge-candidates` only combines already validated candidates and never reads or publishes original books. Then run `git diff --check` and commit:

  ```bash
  git add src/interfaces/cli.py src/interfaces/README.md tests/test_orchestration_cli.py
  git commit -m "feat: 暴露多书候选合并命令"
  ```

### Task 4: 使用现有蒸馏 Skill 完成第一波五本书

**Files:**
- Read only: `configs/ten-book-distillation-plan.json`, `vendor/cangjie/SKILL.md`, `prompts/distillation/01-chapter-extraction.md`, `prompts/distillation/02-book-synthesis.md`, `prompts/distillation/03-evidence-review.md`, `prompts/distillation/04-output-contract.md`, `tools/dev/inventory_books.py`, `src/interfaces/cli.py`
- Runtime-only: `data/jobs/ten-books/wave-1/<book-slug>/`
- Candidate outputs: ignored local directories selected by the operator; do not add them to Git.

**Wave 1 inputs:** `卡片笔记写作法`、`学会提问`、`刻意练习`、`从0到1`、`定位`，按计划文件中的 `order` 执行。

- [ ] **Step 1: Recheck source inventory and headings before creating scopes.**

  Run:

  ```bash
  .venv-mvp/bin/python tools/dev/validate_distillation_plan.py \
    --plan configs/ten-book-distillation-plan.json --check-sources --wave 1
  ```

  For each source, inspect headings without editing the source:

  ```bash
  SOURCE_BOOKS_ROOT=$(jq -r '.source_books_root' configs/local.json)
  rg -n '^(#{1,6})[[:space:]]+' "$SOURCE_BOOKS_ROOT/<source-relative-path>"
  ```

  Record unique `start_heading`/`end_heading` ranges in the runtime scope file. Exclude front matter, recommendation and marketing sections, acknowledgements and references according to the design; do not infer a range from the book title alone.

- [ ] **Step 2: Prepare each book with the existing job script.**

  For each Wave 1 entry, run the existing command with a separate jobs root and separate scope; the command must be equivalent to:

  ```bash
  .venv-mvp/bin/python -m src.interfaces.cli prepare \
    --source "$SOURCE_BOOKS_ROOT/<source-relative-path>" \
    --scope data/jobs/ten-books/wave-1/<book-slug>/scope.json \
    --jobs-root data/jobs/ten-books/wave-1/<book-slug>/prepared \
    --prompts-root prompts/distillation
  ```

  Verify each result contains `document.json`, `source.md`, `units/` and `state.json`; confirm the source hash and the excluded section list before reading units.

- [ ] **Step 3: Run the existing book-distillation Skill and preserve unit outputs.**

  Read `vendor/cangjie/SKILL.md` completely for the current book, then use the existing project prompts. Maintain each book's `PIPELINE_STATE.md`/unit status in the local distillation output, keep candidates and rejected explanations, and store one JSON output per extraction group. Do not create a new Skill, new extractor, or automatic API caller. If a unit fails, retry only that unit and retain successful outputs.

- [ ] **Step 4: Assemble, validate and complete each Wave 1 candidate.**

  Run the existing commands with the actual output files:

  ```bash
  .venv-mvp/bin/python -m src.interfaces.cli assemble \
    --document data/jobs/ten-books/wave-1/<book-slug>/prepared/<job-id>/document.json \
    --output <group-1.json> --output <group-2.json> \
    --destination <book-candidate-dir>
  .venv-mvp/bin/python -m src.interfaces.cli validate <book-candidate-dir>
  .venv-mvp/bin/python -m src.interfaces.cli complete \
    --job data/jobs/ten-books/wave-1/<book-slug>/prepared/<job-id> \
    --output <group-1.json> --output <group-2.json> \
    --candidate <book-candidate-dir>
  ```

  Use one `--output` per actual group; do not use simulated cards or the sample library as evidence of real book quality.

- [ ] **Step 5: Record the semantic gate for each Wave 1 book.**

  In the ignored runtime directory, record at least 12 cross-section card reviews, author/quote attribution decisions, conditions and boundaries, five fixed in-book retrieval questions, and one out-of-scope question. Mark the result `accepted_candidate` only after the agent self-review and root sampling are complete; this record must say it is not an independent human line-by-line audit.

### Task 5: 使用现有蒸馏 Skill 完成第二波五本书

**Files:**
- Read only: same existing Skill, prompts and CLI files as Task 4
- Runtime-only: `data/jobs/ten-books/wave-2/<book-slug>/`
- Candidate outputs: ignored local directories; do not add generated books or evidence to Git.

**Wave 2 inputs:** `穷查理宝典`、`原则`、`稀缺`、`指数基金投资指南`、`经济学的思维方式`，按计划文件中的 `order` 执行。

- [ ] **Step 1: Run the plan/source check and inspect all Wave 2 title boundaries.**

  Run the same validator with `--wave 2`; inspect headings and source quality before creating each scope. Preserve third-party speeches, recommendations and quoted sources as explicitly classified material; do not attribute a compilation's third-party statements to the primary author.

- [ ] **Step 2: Run `prepare` for each Wave 2 source.**

  Use `data/jobs/ten-books/wave-2/<book-slug>/scope.json` and a separate `prepared` directory per book. Confirm the source SHA-256, paragraph count, section count and exclusion list before Agent reading.

- [ ] **Step 3: Run the existing Skill and project prompts per book.**

  Keep extraction group outputs, rejected candidates, pipeline state and token/cost fields exactly as the current workflow defines them. Do not merge the five books at the extraction stage and do not build cross-book claims.

- [ ] **Step 4: Assemble, validate, complete and semantically sample each Wave 2 candidate.**

  Reuse the commands and gates from Task 4. Keep each book independently rerunnable and mark only fully covered, evidence-valid books as `accepted_candidate`.

### Task 6: Build and validate the eleven-book candidate

**Files:**
- Runtime-only: `data/jobs/ten-books/merged/`
- Read only: current published Naval version under `data/library/versions/<CURRENT>`
- Test data runtime-only: `data/jobs/ten-books/evaluation/cases.json` and retrieval output files

- [ ] **Step 1: Enumerate the exact candidate inputs without using the mutable library root as a candidate.**

  Resolve the current Naval candidate with:

  ```bash
  NAVAL_VERSION=$(tr -d '\n' < data/library/CURRENT)
  NAVAL_CANDIDATE="data/library/versions/$NAVAL_VERSION"
  ```

  Collect the 10 `accepted_candidate` directories from Tasks 4–5 in the plan order. Reject the merge if any planned book is missing, blocked, duplicated, or only marked `evaluation_candidate`.

- [ ] **Step 2: Merge without publishing.**

  Run the new CLI with one `--candidate` per input:

  ```bash
  .venv-mvp/bin/python -m src.interfaces.cli merge-candidates \
    --candidate "$NAVAL_CANDIDATE" \
    --candidate <book-1-candidate> --candidate <book-2-candidate> \
    --candidate <book-3-candidate> --candidate <book-4-candidate> \
    --candidate <book-5-candidate> --candidate <book-6-candidate> \
    --candidate <book-7-candidate> --candidate <book-8-candidate> \
    --candidate <book-9-candidate> --candidate <book-10-candidate> \
    --destination data/jobs/ten-books/merged/eleven-book-candidate \
    --library-id library.second-brain-eleven-books \
    --release-status evaluation_candidate
  .venv-mvp/bin/python -m src.interfaces.cli validate \
    data/jobs/ten-books/merged/eleven-book-candidate
  ```

  The merge result must report 11 books, preserve all per-book source fingerprints, contain no cross-book relation edges, and leave `data/library/CURRENT` byte-for-byte unchanged.

- [ ] **Step 3: Check query compatibility with the existing `second-brain` Skill.**

  Run `books`, one book-filtered search per selected book, and one cross-book search against the merged candidate. Read `skills/second-brain/SKILL.md` and use its existing `analyze → validate-analysis` workflow when testing answers. Do not create an eleven-book Skill or a new author Skill; the existing generic Skill already accepts a library path and must continue to distinguish source evidence from system synthesis.

- [ ] **Step 4: Run fixed retrieval and semantic evaluation.**

  Create the ignored `cases.json` only after reading the actual accepted cards. It must contain at least five fixed questions per book and one explicit out-of-scope case per wave, with expected card IDs recorded before the comparison run. Run:

  ```bash
  .venv-mvp/bin/python tools/dev/evaluate_retrieval.py \
    --library data/jobs/ten-books/merged/eleven-book-candidate \
    --cases data/jobs/ten-books/evaluation/cases.json \
    --indexes data/jobs/ten-books/evaluation/indexes \
    --out data/jobs/ten-books/evaluation/merged-retrieval.json
  ```

  Report keyword, semantic, hybrid, negative rejection and evidence correctness separately; do not call top-five recall an answer-quality score.

- [ ] **Step 5: Preserve the old library and record the candidate gate.**

  Write a runtime acceptance record containing the 11-book manifest, candidate version, structural validation result, retrieval result, sampled semantic decisions, known gaps and explicit release status. Do not run `publish` in this task.

### Task 7: Update project documentation without adding a duplicate Skill

**Files:**
- Modify: `docs/distillation-workflow.md`
- Modify: `docs/architecture.md`
- Modify: `docs/README.md`
- Modify: `src/interfaces/README.md`
- Create after real execution: `docs/plans/2026-09-09-ten-book-distillation-execution.md`
- Do not modify: `skills/second-brain/SKILL.md` unless a verified CLI contract change requires it; current path-based library workflow already supports multiple books.

- [ ] **Step 1: Document the new plan validator and merge command.**

  Add the exact commands from Tasks 1 and 6, state that `merge-candidates` consumes validated candidates only, and state that it does not publish or infer cross-book relations.

- [ ] **Step 2: Update architecture status precisely.**

  Replace the current “multiple independent libraries are not automatically merged” statement only after Task 3 is implemented, with the implemented candidate merge boundary. Keep “cross-author graph, automatic queue, model scheduling and semantic expert-group synthesis are not implemented” as explicit limits.

- [ ] **Step 3: Write the real execution record only after the ten-book run.**

  Record actual source hashes, job IDs, counts, status, semantic sampling evidence, retrieval results and unresolved gaps. Never fill this file from the plan or from simulated material.

- [ ] **Step 4: Run Markdown and repository diff checks, then commit documentation.**

  ```bash
  git diff --check
  git add docs/distillation-workflow.md docs/architecture.md docs/README.md src/interfaces/README.md
  git commit -m "docs: 记录多书蒸馏与候选合并流程"
  ```

### Task 8: Final verification and explicit release gate

**Files:**
- Verify: all changed source, tests and documentation from Tasks 1–7
- Never stage: `data/jobs/`, `data/library/versions/` generated candidates, `data/indexes/`, model caches, `configs/local.json`, source books

- [ ] **Step 1: Run the complete code verification suite.**

  ```bash
  .venv-mvp/bin/python -m unittest discover -s tests -p 'test_*.py'
  .venv-mvp/bin/python -m compileall -q src tools/dev
  .venv-mvp/bin/python tools/dev/project_check.py --schemas
  .venv-mvp/bin/python tools/dev/validate_distillation_plan.py \
    --plan configs/ten-book-distillation-plan.json --check-sources
  ```

  Expected: all unit tests pass, compilation returns zero, the existing sample-library check remains green, and all 10 source paths are found.

- [ ] **Step 2: Revalidate every accepted single-book candidate and the merged candidate.**

  Run `src.interfaces.cli validate` for all 10 accepted candidates and for the eleven-book candidate. Confirm every failure names a concrete candidate and that no failure is hidden by `--allow-ready`.

- [ ] **Step 3: Verify current-version immutability.**

  Capture `data/library/CURRENT` before and after merge and compare with `cmp`; run the existing Naval regression retrieval against the unchanged current library. A merge-only run must not change `CURRENT`, existing version bytes or the source root.

- [ ] **Step 4: Verify the final diff and report limitations.**

  Run `git status --short`, `git diff --check`, and `git diff --stat`. Report separately: code tests, source/range status, semantic sampling status, retrieval status, candidate status and whether formal publish was authorized. Do not call the project “ten-book published” until a separate user instruction authorizes `publish` and that command succeeds.
