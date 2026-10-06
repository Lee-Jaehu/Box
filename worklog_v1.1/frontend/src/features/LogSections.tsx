import { useState } from 'react';
import type { Kpi, TrackerRef, User } from '../api/types';
import { RichEditor } from '../editor/RichEditor';
import { emptyDocument, titlePreview } from '../editor/document';
import { uid, type DraftAchievement, type DraftTracker } from '../drafts/logDraft';
import { Field } from '../ui';

// ── 트래커 등록 항목 (신규) ────────────────────────────────────────────────
export function NewTrackerList({ kind, items, users, onChange }: { kind: 'todo' | 'issue'; items: DraftTracker[]; users: User[]; onChange: (items: DraftTracker[]) => void }) {
  const label = kind === 'todo' ? 'To-Do' : 'Issue';
  const patch = (id: string, p: Partial<DraftTracker>) => onChange(items.map((i) => (i.clientEntryId === id ? { ...i, ...p } : i)));
  return (
    <div className="card">
      <h4>{label} 등록 <small className="hint">첫 서버 저장 때 프로젝트 {label}에 등록됩니다. 이후 수정은 {label} 탭에서 합니다.</small></h4>
      {items.map((it, i) => (
        <div key={it.clientEntryId} className="sub-card">
          <RichEditor docKey={it.clientEntryId} value={it.content} images={null} placeholder={`${label} ${i + 1}`} onChange={(content) => patch(it.clientEntryId, { content })} />
          <div className="row">
            <Field label="담당자 (선택)"><select value={it.assigneeId ?? ''} onChange={(e) => patch(it.clientEntryId, { assigneeId: e.target.value || null })}><option value="">미지정</option>{users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></Field>
            <Field label="마감일 (선택)"><input type="date" value={it.dueDate ?? ''} onChange={(e) => patch(it.clientEntryId, { dueDate: e.target.value || null })} /></Field>
            <button type="button" onClick={() => onChange(items.filter((x) => x.clientEntryId !== it.clientEntryId))}>이 항목 취소</button>
          </div>
          {kind === 'issue' && (
            <>
              <Field label="영향 (선택)"><RichEditor docKey={`${it.clientEntryId}-impact`} value={it.impact ?? emptyDocument()} images={null} onChange={(impact) => patch(it.clientEntryId, { impact })} /></Field>
              <Field label="대응 (선택)"><RichEditor docKey={`${it.clientEntryId}-resp`} value={it.response ?? emptyDocument()} images={null} onChange={(response) => patch(it.clientEntryId, { response })} /></Field>
            </>
          )}
        </div>
      ))}
    </div>
  );
}

// ── 이미 등록된 트래커 참조 (읽기 전용 snapshot + 현재 상태) ────────────────
const STATE_TEXT: Record<string, string> = { open: '열림', in_progress: '진행', completed: '완료', cancelled: '취소', resolved: '해결', closed: '종결' };

export function TrackerRefs({ refs, projectId, hidden, onHide }: { refs: TrackerRef[]; projectId: string; hidden: string[]; onHide: (id: string) => void }) {
  const shown = refs.filter((r) => !r.hidden && !hidden.includes(r.id));
  if (!shown.length) return null;
  return (
    <div className="card">
      <h4>이 일지에서 등록한 To-Do / Issue <small className="hint">일지에는 등록 당시 내용이 보존됩니다. 현재 상태는 오른쪽 배지입니다.</small></h4>
      <ul className="refs">
        {shown.map((r) => (
          <li key={r.id}>
            <span className="badge">{r.trackerType === 'todo' ? 'To-Do' : 'Issue'}</span>
            <span className="grow">{titlePreview(r.originalSnapshot.content.doc) || '(내용 없음)'}</span>
            <span className={`badge ${r.current.deleted ? 'bad' : ''}`}>현재: {r.current.deleted ? '삭제됨' : STATE_TEXT[r.current.status ?? ''] ?? r.current.status}</span>
            {!r.current.deleted && <a href={`#/${r.trackerType === 'todo' ? 'todos' : 'issues'}/${projectId}`}>열기</a>}
            <button type="button" title="이 일지의 표시만 숨깁니다. 프로젝트 항목은 그대로입니다." onClick={() => onHide(r.id)}>일지에서 숨기기</button>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── 성과 ───────────────────────────────────────────────────────────────────
const QUANT = [
  ['time_reduction', '시간 단축'], ['cost_reduction', '비용 절감'], ['throughput_increase', '처리량 증가'],
  ['defect_reduction', '오류/불량 감소'], ['goal_achievement', '목표 달성'], ['custom', '직접 입력'],
] as const;
const QUAL: [string, string, string][] = [
  ['standardization', '표준화/체계화', '무엇을 어떻게 표준화했고, 이전과 무엇이 달라졌는지 적어 보세요.'],
  ['quality_stability', '품질/안정성', '어떤 품질·안정성 문제가 어떻게 개선되었는지 적어 보세요.'],
  ['risk_prevention', '리스크 예방', '어떤 위험을 어떻게 미리 막았는지 적어 보세요.'],
  ['collaboration', '협업/의사결정', '협업 방식이나 의사결정이 어떻게 빨라지거나 명확해졌는지 적어 보세요.'],
  ['usability', '사용자 편의', '사용자가 무엇이 편해졌는지 적어 보세요.'],
  ['knowledge', '지식 축적/전파', '무엇을 정리·공유했고 누가 활용할 수 있는지 적어 보세요.'],
  ['custom', '직접 작성', '무엇을 했고 무엇이 달라졌는지 적어 보세요.'],
];
const REDUCE = new Set(['time_reduction', 'cost_reduction', 'defect_reduction']);

/** 입력 중 참고용 계산(서버가 저장 시 Decimal 로 다시 계산한다). */
function hint(a: DraftAchievement): string | null {
  const n = a.numeric;
  const before = Number(n.beforeValue), after = Number(n.afterValue);
  if (a.type !== 'quantitative' || ['goal_achievement', 'custom'].includes(a.presetKey)) return null;
  if (!n.beforeValue || !n.afterValue || Number.isNaN(before) || Number.isNaN(after)) return null;
  const diff = after - before;
  const good = REDUCE.has(a.presetKey) ? diff < 0 : diff > 0;
  const rel = before === 0 ? '변화율 계산 불가(기존 0)' : `${((diff / before) * 100).toFixed(1)}%`;
  const pp = n.unit === '%' ? ` · ${diff > 0 ? '+' : ''}${diff}%p` : '';
  return `예상: ${diff > 0 ? '+' : ''}${diff}${n.unit ?? ''} (${rel})${pp} — ${diff === 0 ? '변화 없음' : good ? '개선' : '악화'} · 저장 시 서버가 다시 계산합니다.`;
}

export function AchievementList({ items, kpis, today, onChange }: { items: DraftAchievement[]; kpis: Kpi[]; today: string; onChange: (items: DraftAchievement[]) => void }) {
  const patch = (id: string, p: Partial<DraftAchievement>) => onChange(items.map((i) => (i.id === id ? { ...i, ...p } : i)));
  const setNum = (a: DraftAchievement, k: string, v: string) => patch(a.id, { numeric: { ...a.numeric, [k]: v } });
  return (
    <div className="card">
      <h4>성과 <small className="hint">선택 입력입니다. TASK는 ‘활동’, 성과는 ‘변화/결과’입니다.</small></h4>
      {items.map((a) => {
        const kpi = kpis.find((k) => k.id === a.kpiId);
        const qual = QUAL.find((q) => q[0] === a.presetKey);
        const compare = !['goal_achievement', 'custom'].includes(a.presetKey);
        return (
          <div key={a.id} className="sub-card">
            <div className="row">
              <Field label="유형">
                <select value={a.type === 'quantitative' ? 'q' : 'l'} onChange={(e) => patch(a.id, e.target.value === 'q' ? { type: 'quantitative', presetKey: 'time_reduction' } : { type: 'qualitative', presetKey: 'standardization', kpiId: null })}>
                  <option value="q">정량</option><option value="l">정성</option>
                </select>
              </Field>
              <Field label="프리셋">
                <select value={a.presetKey} onChange={(e) => patch(a.id, { presetKey: e.target.value })}>
                  {(a.type === 'quantitative' ? QUANT.map(([k, l]) => [k, l] as const) : QUAL.map(([k, l]) => [k, l] as const)).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select>
              </Field>
              <Field label="제목 (선택)"><input value={a.title} onChange={(e) => patch(a.id, { title: e.target.value })} /></Field>
              <button type="button" onClick={() => onChange(items.filter((x) => x.id !== a.id))}>삭제</button>
            </div>
            {a.type === 'quantitative' ? (
              <>
                <div className="row">
                  <Field label="KPI 연결 (선택)">
                    <select value={a.kpiId ?? ''} onChange={(e) => {
                      const k = kpis.find((x) => x.id === e.target.value);
                      patch(a.id, { kpiId: k?.id ?? null, numeric: k ? { ...a.numeric, metricName: a.numeric.metricName || k.name, unit: a.numeric.unit || (k.unit ?? ''), ...(a.presetKey === 'goal_achievement' && k.targetValue ? { targetValue: a.numeric.targetValue || k.targetValue } : {}) } : a.numeric });
                    }}>
                      <option value="">연결 안 함</option>
                      {kpis.filter((k) => k.active).map((k) => <option key={k.id} value={k.id}>{k.name}{k.unit ? ` (${k.unit})` : ''}</option>)}
                    </select>
                  </Field>
                  {kpi && <small className="hint">KPI 기준값 {kpi.baselineValue ?? '—'} · 목표 {kpi.targetValue ?? '—'}. 이번 측정값은 아래에서 확인/변경하세요. KPI 실적을 덮어쓰거나 합산하지 않습니다.</small>}
                </div>
                <div className="row">
                  <Field label="지표명"><input value={a.numeric.metricName ?? ''} onChange={(e) => setNum(a, 'metricName', e.target.value)} /></Field>
                  {compare && <><Field label="기존 값"><input inputMode="decimal" value={a.numeric.beforeValue ?? ''} onChange={(e) => setNum(a, 'beforeValue', e.target.value)} /></Field>
                    <Field label="현재 값"><input inputMode="decimal" value={a.numeric.afterValue ?? ''} onChange={(e) => setNum(a, 'afterValue', e.target.value)} /></Field></>}
                  {a.presetKey === 'goal_achievement' && <><Field label="목표"><input inputMode="decimal" value={a.numeric.targetValue ?? ''} onChange={(e) => setNum(a, 'targetValue', e.target.value)} /></Field>
                    <Field label="실적"><input inputMode="decimal" value={a.numeric.value ?? ''} onChange={(e) => setNum(a, 'value', e.target.value)} /></Field></>}
                  {a.presetKey === 'custom' && <Field label="값"><input inputMode="decimal" value={a.numeric.value ?? ''} onChange={(e) => setNum(a, 'value', e.target.value)} /></Field>}
                  <Field label="단위"><input value={a.numeric.unit ?? ''} onChange={(e) => setNum(a, 'unit', e.target.value)} placeholder="분/건, %, 원…" /></Field>
                  {a.presetKey === 'cost_reduction' && <Field label="통화"><input value={a.numeric.currency ?? ''} onChange={(e) => setNum(a, 'currency', e.target.value)} placeholder="KRW" /></Field>}
                </div>
                <div className="row">
                  <Field label="비교 기준/기간" hint="기존·현재 값이 같은 기준일 때만 비교합니다."><input value={a.numeric.comparisonBasis ?? ''} onChange={(e) => setNum(a, 'comparisonBasis', e.target.value)} /></Field>
                  <Field label="측정 범위"><input value={a.numeric.measurementScope ?? ''} onChange={(e) => setNum(a, 'measurementScope', e.target.value)} /></Field>
                  <Field label="측정일"><input type="date" value={a.measuredOn ?? ''} onChange={(e) => patch(a.id, { measuredOn: e.target.value || null })} /></Field>
                  <Field label="대상 기간 시작"><input type="date" value={a.periodStart ?? ''} onChange={(e) => patch(a.id, { periodStart: e.target.value || null })} /></Field>
                  <Field label="종료"><input type="date" value={a.periodEnd ?? ''} onChange={(e) => patch(a.id, { periodEnd: e.target.value || null })} /></Field>
                </div>
                {hint(a) && <p className="hint">{hint(a)}</p>}
                <Field label="설명 (선택)"><RichEditor docKey={`${a.id}-c`} value={a.content ?? emptyDocument()} images={null} onChange={(content) => patch(a.id, { content })} /></Field>
              </>
            ) : (
              <Field label="내용" hint={qual?.[2]}>
                <RichEditor docKey={`${a.id}-q`} value={a.content ?? emptyDocument()} images={null} placeholder={qual?.[2]} onChange={(content) => patch(a.id, { content })} />
              </Field>
            )}
          </div>
        );
      })}
      <div className="row">
        <button type="button" onClick={() => onChange([...items, { id: uid(), type: 'quantitative', presetKey: 'time_reduction', title: '', content: null, numeric: {}, kpiId: null, measuredOn: today, periodStart: null, periodEnd: null }])}>+ 정량 성과</button>
        <button type="button" onClick={() => onChange([...items, { id: uid(), type: 'qualitative', presetKey: 'standardization', title: '', content: null, numeric: {}, kpiId: null, measuredOn: today, periodStart: null, periodEnd: null }])}>+ 정성 성과</button>
      </div>
    </div>
  );
}

export function Collaborators({ ids, users, onChange }: { ids: string[]; users: User[]; onChange: (ids: string[]) => void }) {
  const [pick, setPick] = useState('');
  return (
    <div className="card">
      <h4>협업자 <small className="hint">프로젝트 참여자와 별개로, 이번 기록과 관련된 사람입니다.</small></h4>
      <div className="row">
        {ids.map((id) => <span key={id} className="chip">{users.find((u) => u.id === id)?.name ?? id}<button type="button" aria-label="제거" onClick={() => onChange(ids.filter((x) => x !== id))}>×</button></span>)}
        <select value={pick} onChange={(e) => { if (e.target.value) onChange([...new Set([...ids, e.target.value])]); setPick(''); }}>
          <option value="">+ 추가…</option>
          {users.filter((u) => !ids.includes(u.id)).map((u) => <option key={u.id} value={u.id}>{u.name}{u.teamName ? ` · ${u.teamName}` : ''}</option>)}
        </select>
      </div>
    </div>
  );
}
