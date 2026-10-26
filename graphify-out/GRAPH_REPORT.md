# Graph Report - reels-second-brain  (2026-10-26)

## Corpus Check
- Corpus is ~14,886 words - fits in a single context window. You may not need a graph.

## Summary
- 384 nodes · 897 edges · 16 communities (15 shown, 1 thin omitted)
- Extraction: 85% EXTRACTED · 15% INFERRED · 0% AMBIGUOUS · INFERRED: 132 edges (avg confidence: 0.89)
- Token cost: 102,750 input · 0 output

## Community Hubs (Navigation)
- Config & Media Utilities
- FastAPI App & Kakao OAuth
- Worker Loop & Tests
- Media Tests & URL Safety
- Test Fixtures & Webhook Tests
- Instagram Webhook Parsing
- Kakao Send Client
- Collaboration Rules
- Knowledge Layer Decisions
- Stage 1 Schema & Review
- Speech Transcription
- Job Handlers
- PRD Roadmap & Gates
- Media Module Contracts
- Intake Reliability & Queue
- Package Root

## God Nodes (most connected - your core abstractions)
1. `Worker` - 26 edges
2. `receive()` - 19 edges
3. `make_deps()` - 18 edges
4. `Settings` - 17 edges
5. `create_app()` - 16 edges
6. `Segment` - 15 edges
7. `ExtractionResult` - 15 edges
8. `load_fixture()` - 15 edges
9. `post()` - 14 edges
10. `Limits` - 13 edges

## Surprising Connections (you probably didn't know these)
- `test_frames()` --uses--> `Limits`  [INFERRED]
  tests/media/test_media.py → src/rsb/media/types.py
- `webhook_receive()` --indirect_call--> `conn()`  [INFERRED]
  src/rsb/app.py → tests/conftest.py
- `kakao_login()` --indirect_call--> `conn()`  [INFERRED]
  src/rsb/app.py → tests/conftest.py
- `kakao_callback()` --indirect_call--> `conn()`  [INFERRED]
  src/rsb/app.py → tests/conftest.py
- `kakao_test_send()` --indirect_call--> `conn()`  [INFERRED]
  src/rsb/app.py → tests/conftest.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **D15 Durable Intake Flow (verify, persist, 200, worker)** — docs_prd_d15_intake_reliability, docs_prd_instagram_webhook_interface, docs_prd_table_webhook_events, docs_prd_table_jobs, docs_prd_table_intakes, docs_prd_postgres_jobs_queue [EXTRACTED 1.00]
- **Stage 1 Media Extraction Modules** — docs_module_contracts_fetch_video, docs_module_contracts_sample_frames, docs_module_contracts_extract_screen_text, docs_module_contracts_extract_speech, agents_codex_media_scope, docs_prd_table_extractions [INFERRED 0.85]
- **[가설] Payload Hypothesis Verification Loop** — docs_prd_ig_reel_attachment_hypothesis, docs_stage1_runbook_hypothesis_checks, tests_fixtures_mock_readme_mock_payloads, docs_review_codex_reel_dedup_issue, docs_prd_labeling_convention [INFERRED 0.85]

## Communities (16 total, 1 thin omitted)

### Community 0 - "Config & Media Utilities"
Cohesion: 0.07
Nodes (18): BlockedURLError, check_public_url(), fetch_video(), _hash(), sample_frames(), extract_screen_text(), OpenAIVisionReader, extract_speech() (+10 more)

### Community 1 - "FastAPI App & Kakao OAuth"
Cohesion: 0.08
Nodes (22): create_app(), kakao_callback(), kakao_login(), kakao_test_send(), require_admin(), main(), get_settings(), Settings (+14 more)

### Community 2 - "Worker Loop & Tests"
Cohesion: 0.12
Nodes (26): FetchResult, Worker, drain(), FakeT, FakeV, make_deps(), default_fetch(), receive() (+18 more)

### Community 3 - "Media Tests & URL Safety"
Cohesion: 0.08
Nodes (21): public_dns(), Reader, test_blocked(), test_consecutive_ocr(), test_direct(), test_frames(), test_ocr(), test_openai_backends() (+13 more)

### Community 4 - "Test Fixtures & Webhook Tests"
Cohesion: 0.15
Nodes (21): conn(), database_url(), load_fixture(), settings(), sign(), client(), count(), post() (+13 more)

### Community 5 - "Instagram Webhook Parsing"
Cohesion: 0.11
Nodes (13): webhook_receive(), classify(), IncomingMessage, parse_entries(), ReelAttachment, verify_signature(), record_message(), _reply_text() (+5 more)

### Community 6 - "Kakao Send Client"
Cohesion: 0.13
Nodes (13): send_text(), client(), fake(), FakeKakao, login(), test_expired_state_rejected(), test_login_flow_stores_encrypted_tokens(), test_other_kakao_user_rejected() (+5 more)

### Community 7 - "Collaboration Rules"
Cohesion: 0.19
Nodes (11): Codex Instructions (AGENTS.md), Codex Scope: src/rsb/media modules (fetch, frames, ocr, transcribe), Tests Run Without Network or API Keys, Claude Code Instructions (CLAUDE.md), Role Split: Claude Code vs Codex, check_public_url / BlockedURLError, Argument-array Subprocess Invocation with Limits, Treat Video/Caption/Web Content as Data, Not Instructions (+3 more)

### Community 8 - "Knowledge Layer Decisions"
Cohesion: 0.17
Nodes (8): Analysis and Enrichment Pipeline (6 stages), Kakao Send-to-Me (archive path, 8.2), Knowledge Layer (tips, claims, evidence, tip_relations, digests, feedback, kakao_tokens), LLM Output Contract (Stage 2 draft), System Mechanical Checks (excerpt string match), Mobile Web (8.3), Weekly Digest Selection and Sending (8.4), Kakao Login and Test Send Procedure

### Community 9 - "Stage 1 Schema & Review"
Cohesion: 0.24
Nodes (14): extractor_version format <module>@<version>+<backend>, Send API 24-hour Reply Window, System Architecture (webhook server + analysis worker), extractions table, intakes table, processing_runs table, reels table, webhook_events table (+6 more)

### Community 10 - "Speech Transcription"
Cohesion: 0.20
Nodes (6): FasterWhisperTranscriber, OpenAIWhisperTranscriber, Segment, make_transcriber(), Speech, test_speech()

### Community 11 - "Job Handlers"
Cohesion: 0.27
Nodes (4): PermanentError, _reel(), _save_caption(), _save_extraction()

### Community 12 - "PRD Roadmap & Gates"
Cohesion: 0.20
Nodes (10): Deferred Items and Future Extensions (Ch.13), Reels Second Brain PRD, Pre-preparation Checklist (Ch.12), Reels Second Brain PoC (single-user), Risks and Constraints (Ch.10), Stage 1 Gate: 4 of 5 reels fetched and extracted, Staged Rollout (Stage 1/2/3 with gates), Validation Plan and Gates (Ch.9) (+2 more)

### Community 13 - "Media Module Contracts"
Cohesion: 0.22
Nodes (9): Backends: OpenAIVisionReader, OpenAIWhisperTranscriber, FasterWhisperTranscriber, extract_screen_text, extract_speech, fetch_video, Stage 1 Media Module I/O Contracts, sample_frames, Recommended Tech Stack (FastAPI, Postgres+pgvector, Whisper, vision LLM), Whisper (API or faster-whisper) (+1 more)

### Community 14 - "Intake Reliability & Queue"
Cohesion: 0.25
Nodes (6): [가설] ig_reel Attachment Payload, Instagram Webhook Interface (8.1), PostgreSQL jobs Table Queue (FOR UPDATE SKIP LOCKED), jobs table, Meta Webhook Setup and Sender Allowlist, Mock Payloads (hand-made, not real)

## Knowledge Gaps
- **9 isolated node(s):** `rsb`, `Reels Second Brain PoC (single-user)`, `System Mechanical Checks (excerpt string match)`, `LLM Output Contract (Stage 2 draft)`, `Mobile Web (8.3)` (+4 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 98 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Worker` connect `Worker Loop & Tests` to `Config & Media Utilities`, `FastAPI App & Kakao OAuth`, `Job Handlers`?**
  _High betweenness centrality (0.060) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `Worker` (e.g. with `Settings` and `ExtractionResult`) actually correct?**
  _`Worker` has 14 INFERRED edges - model-reasoned connections that need verification._
- **What connects `rsb`, `Reels Second Brain PoC (single-user)`, `System Mechanical Checks (excerpt string match)` to the rest of the system?**
  _9 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Config & Media Utilities` be split into smaller, more focused modules?**
  _Cohesion score 0.073224043715847 - nodes in this community are weakly interconnected._
- **Why does `Codex Scope: src/rsb/media modules (fetch, frames, ocr, transcribe)` connect `Collaboration Rules` to `Config & Media Utilities`, `Media Module Contracts`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `receive()` (e.g. with `IncomingMessage` and `ReelAttachment`) actually correct?**
  _`receive()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Should `FastAPI App & Kakao OAuth` be split into smaller, more focused modules?**
  _Cohesion score 0.08127721335268505 - nodes in this community are weakly interconnected._