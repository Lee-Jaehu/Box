import { act, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it } from 'vitest';
import { useDraft } from './ProjectPicker';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let api: { applied: { q: string }; draft: { q: string }; dirty: boolean; setDraft: (v: { q: string }) => void; apply: () => void; setApplied: (v: { q: string }) => void; fetches: string[] };

function Harness() {
  const [applied, setApplied] = useState({ q: '' });
  const fetches = useState<string[]>([])[0];
  // 조회는 applied 가 바뀔 때만 일어난다고 가정하고, 그 횟수를 기록한다
  if (fetches[fetches.length - 1] !== applied.q) fetches.push(applied.q);
  const d = useDraft(applied, setApplied);
  api = { applied, draft: d.draft, dirty: d.dirty, setDraft: d.setDraft, apply: d.apply, setApplied, fetches };
  return null;
}

describe('useDraft (filters apply only on the button)', () => {
  it('typing changes the draft but not the applied filter; apply commits it; outside changes sync back', async () => {
    const host = document.createElement('div');
    const root = createRoot(host);
    await act(async () => root.render(<Harness />));
    expect(api.dirty).toBe(false);

    await act(async () => api.setDraft({ q: '품질' }));
    expect(api.draft.q).toBe('품질');
    expect(api.applied.q).toBe('');          // 아직 적용 전: 조회 조건은 그대로
    expect(api.dirty).toBe(true);            // ‘필터 적용’ 필요 표시
    expect(api.fetches).toEqual(['']);       // 조회가 다시 일어나지 않았다

    await act(async () => api.apply());
    expect(api.applied.q).toBe('품질');
    expect(api.dirty).toBe(false);
    expect(api.fetches).toEqual(['', '품질']);

    await act(async () => api.setDraft({ q: '다시 입력' }));
    await act(async () => api.setApplied({ q: '' }));     // 초기화처럼 바깥에서 적용값이 바뀌면
    expect(api.draft.q).toBe('');                          // 입력칸도 맞춰진다
    expect(api.dirty).toBe(false);
    await act(async () => root.unmount());
  });

  it('applying the same value again is a no-op', async () => {
    const host = document.createElement('div');
    const root = createRoot(host);
    await act(async () => root.render(<Harness />));
    await act(async () => api.apply());
    expect(api.fetches).toEqual(['']);
    await act(async () => root.unmount());
  });
});
