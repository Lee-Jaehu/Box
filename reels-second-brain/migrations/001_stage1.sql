-- 1단계 테이블 (PRD 6장 초안 + 1단계 구현에 필요한 보완)
-- 보완: jobs.payload/run_after/result/updated_at, processing_runs, kakao_tokens, oauth_states

CREATE TABLE webhook_events (
  id BIGSERIAL PRIMARY KEY,
  message_id TEXT UNIQUE NOT NULL,     -- 재전달 중복 차단
  sender_id TEXT NOT NULL,
  recipient_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('reel','text','unsupported','ignored')),
  payload JSONB NOT NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE reels (
  id BIGSERIAL PRIMARY KEY,
  ig_video_id TEXT UNIQUE,
  url TEXT NOT NULL,
  caption TEXT,
  fetch_status TEXT NOT NULL DEFAULT 'pending' CHECK (fetch_status IN ('pending','fetched','failed')),
  fetch_error TEXT,
  fetch_method TEXT,
  video_path TEXT,
  video_delete_after TIMESTAMPTZ,      -- 2단계 채점 후 삭제 시각. NULL이면 보존
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE jobs (
  id BIGSERIAL PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('fetch','transcribe','ocr','reply')),  -- kind가 곧 단계(stage)
  reel_id BIGINT REFERENCES reels(id),
  payload JSONB NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed')),
  attempts INT NOT NULL DEFAULT 0,
  run_after TIMESTAMPTZ NOT NULL DEFAULT now(),  -- 재시도 대기
  lease_until TIMESTAMPTZ,             -- 워커가 죽으면 만료 후 재수거
  last_error TEXT,
  result JSONB,
  idempotency_key TEXT UNIQUE,         -- 같은 작업 중복 등록 방지
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX jobs_ready_idx ON jobs (run_after) WHERE status IN ('queued','running');

CREATE TABLE intakes (
  id BIGSERIAL PRIMARY KEY,
  reel_id BIGINT NOT NULL REFERENCES reels(id),
  event_id BIGINT REFERENCES webhook_events(id),
  source TEXT NOT NULL CHECK (source IN ('dm','export')),
  note TEXT,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE extractions (
  id BIGSERIAL PRIMARY KEY,
  reel_id BIGINT NOT NULL REFERENCES reels(id),
  medium TEXT NOT NULL CHECK (medium IN ('audio','screen','caption')),
  status TEXT NOT NULL CHECK (status IN ('pending','succeeded','failed','empty')),
  text TEXT,
  segments JSONB,                      -- [{start, end, text}] 또는 [{frame_ts, text}]
  error TEXT,
  extractor_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (reel_id, medium, extractor_version)
);

CREATE TABLE processing_runs (
  id BIGSERIAL PRIMARY KEY,
  reel_id BIGINT REFERENCES reels(id),
  job_id BIGINT REFERENCES jobs(id),
  stage TEXT NOT NULL,
  model TEXT,
  prompt_version TEXT,
  outcome TEXT,
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  cost_estimate NUMERIC(10,4)
);

-- 단일 사용자(재후) 토큰. 값은 애플리케이션에서 암호화해 저장
CREATE TABLE kakao_tokens (
  kakao_user_id TEXT PRIMARY KEY,
  access_token_enc TEXT NOT NULL,
  refresh_token_enc TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  refresh_expires_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE oauth_states (
  state TEXT PRIMARY KEY,
  expires_at TIMESTAMPTZ NOT NULL
);
