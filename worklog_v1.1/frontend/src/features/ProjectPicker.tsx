import { useEffect, useMemo, useState } from 'react';
import type { Project } from '../api/types';
import { Field, STATUS_LABEL, useSession } from '../ui';
import { defaultFilters, filterProjects, loadFilters, saveFilters, uniqueOptions, type PickerFilters } from './projectFilter';

/** 적용된 필터(브라우저에 기억). 로그인한 사용자가 아니라 ‘상단에서 고른 작성자’ 기준으로 기본값(내 프로젝트)을 정한다. */
export function usePickerFilters(): [PickerFilters, (f: PickerFilters) => void] {
  const { actor } = useSession();
  const [f, setF] = useState<PickerFilters>(() => loadFilters(!!actor));
  useEffect(() => { saveFilters(f); }, [f]);
  return [f, setF];
}

/** 필터 입력(초안)과 ‘적용된’ 필터를 분리하는 공통 훅. 적용 버튼/Enter 를 눌러야 applied 가 바뀐다. */
export function useDraft<T>(applied: T, onApply: (v: T) => void) {
  const [draft, setDraft] = useState<T>(applied);
  const key = JSON.stringify(applied);
  useEffect(() => { setDraft(applied); }, [key]); // eslint-disable-line react-hooks/exhaustive-deps  (밖에서 적용값이 바뀌면 입력칸도 맞춘다)
  const dirty = JSON.stringify(draft) !== key;
  return { draft, setDraft, dirty, apply: () => onApply(draft) };
}

/** 필터 영역 공통 버튼: 변경하면 ‘적용 필요’ 표시, 적용/초기화 */
export function ApplyButtons({ dirty, onApply, onReset }: { dirty: boolean; onApply: () => void; onReset: () => void }) {
  return (
    <div className="apply-bar">
      <button type="button" className="primary" disabled={!dirty} onClick={onApply}>필터 적용</button>
      <button type="button" onClick={onReset}>초기화</button>
      {dirty && <small className="warn-text" role="status">조건이 바뀌었습니다. ‘필터 적용’을 누르면 반영됩니다.</small>}
    </div>
  );
}

/** Enter 로도 적용할 수 있게 하는 key handler */
export const onEnter = (fn: () => void) => (e: React.KeyboardEvent) => { if (e.key === 'Enter') { e.preventDefault(); fn(); } };

interface FilterBarProps {
  projects: Project[];
  filters: PickerFilters;
  onChange: (f: PickerFilters) => void;
  onEnter?: () => void;
}

export function FilterBar({ projects, filters, onChange, onEnter: enter }: FilterBarProps) {
  const { actor } = useSession();
  const divisions = useMemo(() => uniqueOptions(projects, 'division'), [projects]);
  const teams = useMemo(() => uniqueOptions(projects.filter((p) => !filters.divisionId || p.divisionId === filters.divisionId), 'team'), [projects, filters.divisionId]);
  const set = (p: Partial<PickerFilters>) => onChange({ ...filters, ...p });
  return (
    <>
      <Field label="범위" hint={!actor ? '작성자를 선택하면 내 프로젝트만 볼 수 있어요' : undefined}>
        <select value={actor ? filters.scope : 'all'} disabled={!actor} onChange={(e) => set({ scope: e.target.value as 'mine' | 'all' })}>
          <option value="mine">내 프로젝트</option>
          <option value="all">전체 프로젝트</option>
        </select>
      </Field>
      <Field label="담당 조직"><select value={filters.divisionId} onChange={(e) => set({ divisionId: e.target.value, teamId: '' })}><option value="">전체</option>{divisions.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></Field>
      <Field label="팀"><select value={filters.teamId} onChange={(e) => set({ teamId: e.target.value })}><option value="">전체</option>{teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
      <Field label="상태"><select value={filters.status} onChange={(e) => set({ status: e.target.value })}><option value="">전체</option>{['preparing', 'in_progress', 'on_hold', 'completed', 'cancelled'].map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}</select></Field>
      <Field label="이름 검색"><input value={filters.q} onChange={(e) => set({ q: e.target.value })} onKeyDown={enter ? onEnter(enter) : undefined} placeholder="프로젝트명 (Enter로 적용)" /></Field>
    </>
  );
}

interface PickerProps {
  projects: Project[];
  value: string;
  onChange: (id: string) => void;
  filters: PickerFilters;
  onFiltersChange: (f: PickerFilters) => void;
  /** true: ‘프로젝트’ 칸도 필터의 일부(비어 있으면 필터에 맞는 모든 프로젝트)라서 ‘필터 적용’ 때 함께 반영된다 */
  allowAll?: boolean;
  /** 작성자 범위 필터(선택). 업무일지 조회에서 ‘내가 쓴 일지만’ */
  author?: { me: boolean; onChange: (me: boolean) => void };
  label?: string;
  hasActor?: boolean;
}

/**
 * 프로젝트 드롭박스 + 바로 옆 필터.
 * - 필터(범위/조직/팀/상태/이름)는 ‘필터 적용’(또는 이름 칸 Enter)을 눌러야 드롭박스 목록과 조회 결과에 반영된다.
 * - allowAll=false(작성 시작, To-Do/Issue): 프로젝트를 고르는 것은 선택 동작이라 바로 반영된다.
 * - allowAll=true(업무일지 조회): 프로젝트 칸과 작성자 범위도 필터이므로 적용 버튼으로 함께 반영된다.
 */
export function ProjectPicker({ projects, value, onChange, filters, onFiltersChange, allowAll, author, label = '프로젝트' }: PickerProps) {
  const { actor } = useSession();
  const applied = useMemo(() => ({ filters, value: allowAll ? value : '', me: author?.me ?? false }), [filters, value, allowAll, author?.me]);
  const { draft, setDraft, dirty, apply } = useDraft(applied, (d) => {
    onFiltersChange(d.filters);
    if (allowAll) onChange(d.value);
    author?.onChange(d.me);
  });
  const shown = useMemo(() => filterProjects(projects, filters, actor?.id ?? null), [projects, filters, actor]); // 드롭박스 = 적용된 필터 기준
  const current = allowAll ? draft.value : value;
  const selected = projects.find((p) => p.id === current);
  const options = selected && !shown.some((p) => p.id === selected.id) ? [selected, ...shown] : shown;
  const reset = () => {
    const f = defaultFilters(!!actor);
    setDraft({ filters: f, value: '', me: false });
    onFiltersChange(f);
    if (allowAll) onChange('');
    author?.onChange(false);
  };
  return (
    <div className="row picker">
      <Field label={`${label} (${shown.length})`}>
        <select value={current} onChange={(e) => (allowAll ? setDraft({ ...draft, value: e.target.value }) : onChange(e.target.value))} style={{ minWidth: 260 }}>
          <option value="">{allowAll ? '필터에 맞는 모든 프로젝트' : '프로젝트를 선택하세요…'}</option>
          {options.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.teamName} · {STATUS_LABEL[p.status]}</option>)}
        </select>
      </Field>
      <FilterBar projects={projects} filters={draft.filters} onChange={(f) => setDraft({ ...draft, filters: f })} onEnter={apply} />
      {author && (
        <Field label="작성자">
          <select value={draft.me ? 'me' : 'all'} disabled={!actor} onChange={(e) => setDraft({ ...draft, me: e.target.value === 'me' })}>
            <option value="all">모든 담당자</option><option value="me">내가 쓴 일지만</option>
          </select>
        </Field>
      )}
      <ApplyButtons dirty={dirty} onApply={apply} onReset={reset} />
      {shown.length === 0 && <small className="hint">조건에 맞는 프로젝트가 없습니다. 필터를 바꿔 ‘필터 적용’을 눌러 보세요.</small>}
    </div>
  );
}
