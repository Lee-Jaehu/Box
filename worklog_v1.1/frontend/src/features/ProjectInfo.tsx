import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import type { Kpi, List, Milestone, Org, Project } from '../api/types';
import { RichEditor } from '../editor/RichEditor';
import { emptyDocument, type WorklogDocument } from '../editor/document';
import type { GanttViewMode } from '../gantt/adapter';
import { Field, STATUS_LABEL, errText, useAsync, useSession, useToast } from '../ui';
import { MilestoneGantt } from './MilestoneGantt';
import { candidateUsers, ownerAfterTeamChange } from './teamUsers';

interface Props { project: Project; reload: () => void }

interface Form {
  name: string; teamId: string; status: string; ownerUserId: string; memberIds: string[];
  isShortTerm: boolean; startDate: string; endDate: string;
}
const toForm = (p: Project): Form => ({
  name: p.name, teamId: p.teamId, status: p.status, ownerUserId: p.ownerUserId, memberIds: [...p.memberIds].sort(),
  isShortTerm: p.isShortTerm, startDate: p.startDate ?? '', endDate: p.endDate ?? '',
});

type MsEdit = Partial<{ name: string; status: string; plannedStart: string; plannedEnd: string; actualStart: string; actualEnd: string }>;

export function ProjectInfo({ project, reload }: Props) {
  const toast = useToast();
  const { users } = useSession();
  const orgs = useAsync(() => api.get<List<Org>>('/organizations?limit=200'), []);
  const teams = (orgs.data?.items ?? []).filter((o) => o.kind === 'team' && (o.active || o.id === project.teamId));
  const [busy, setBusy] = useState(false);
  const [otherTeams, setOtherTeams] = useState(false);
  const act = async (fn: () => Promise<unknown>, ok?: string): Promise<boolean> => {
    setBusy(true);
    try { await fn(); if (ok) toast('ok', ok); reload(); return true; } catch (e) { toast('err', errText(e)); reload(); return false; } finally { setBusy(false); }
  };

  // ── 기본 정보 (명시적 저장) ──
  const [form, setForm] = useState<Form>(() => toForm(project));
  useEffect(() => { setForm(toForm(project)); }, [project.revision, project.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const base = useMemo(() => toForm(project), [project]);
  const dirty = JSON.stringify({ ...form, memberIds: [...form.memberIds].sort() }) !== JSON.stringify(base);
  const dateError = form.startDate && form.endDate && form.endDate < form.startDate ? '종료일은 시작일보다 빠를 수 없습니다.' : '';
  const saveBasic = () => act(async () => {
    const body: Record<string, unknown> = { expectedRevision: project.revision };
    if (form.name !== base.name) body.name = form.name.trim();
    if (form.teamId !== base.teamId) body.teamId = form.teamId;
    if (form.status !== base.status) body.status = form.status;
    if (form.ownerUserId !== base.ownerUserId) body.ownerUserId = form.ownerUserId;
    if (JSON.stringify(form.memberIds) !== JSON.stringify(base.memberIds) || form.ownerUserId !== base.ownerUserId) body.memberIds = form.memberIds;
    if (form.isShortTerm !== base.isShortTerm) body.isShortTerm = form.isShortTerm;
    if (form.startDate !== base.startDate) body.startDate = form.startDate || null;
    if (form.endDate !== base.endDate) body.endDate = form.endDate || null;
    await api.patch(`/projects/${project.id}`, body);
  }, '프로젝트 기본 정보를 저장했습니다.');

  const [view, setView] = useState<GanttViewMode>('Week');
  const [msName, setMsName] = useState('');
  const [msEdits, setMsEdits] = useState<Record<string, MsEdit>>({});
  const [kpi, setKpi] = useState({ name: '', unit: '', baselineValue: '', targetValue: '', direction: '' });
  const [bg, setBg] = useState<WorklogDocument | null>(null);
  const [purpose, setPurpose] = useState<WorklogDocument | null>(null);
  // 저장 후 프로젝트가 새 revision 으로 다시 로드되면 임시 편집 상태를 비운다(에디터도 새 revision 키로 다시 만들어진다).
  useEffect(() => { setBg(null); setPurpose(null); }, [project.revision, project.id]);
  // '변경됨'은 입력 이벤트가 있었는지가 아니라 저장된 내용과 실제로 다른지로 판단한다.
  const sameDoc = (a: WorklogDocument | null, b: WorklogDocument | null | undefined) => JSON.stringify(a?.doc) === JSON.stringify((b ?? emptyDocument()).doc);
  const bgDirty = !!bg && !sameDoc(bg, project.backgroundDoc);
  const purposeDirty = !!purpose && !sameDoc(purpose, project.purposeDoc);
  const textDirty = bgDirty || purposeDirty;
  const [showDetail, setShowDetail] = useState(!project.isShortTerm);
  useEffect(() => { setMsEdits({}); }, [project.revision]);
  const ms = project.milestones ?? [];
  const kpis = project.kpis ?? [];
  const detail = project.hasDetail;

  const patchMs = (m: Milestone, body: Record<string, unknown>, ok?: string) => act(() => api.patch(`/milestones/${m.id}`, { expectedRevision: m.revision, ...body }), ok);
  const saveMs = async (m: Milestone) => {
    const e = msEdits[m.id];
    if (!e) return;
    const body: Record<string, unknown> = {};
    for (const k of Object.keys(e) as (keyof MsEdit)[]) body[k] = e[k] === '' ? null : e[k];
    if (await patchMs(m, body, '마일스톤을 저장했습니다.')) setMsEdits(({ [m.id]: _drop, ...rest }) => rest);
  };
  const setE = (m: Milestone, p: MsEdit) => setMsEdits((s) => ({ ...s, [m.id]: { ...s[m.id], ...p } }));
  const val = <K extends keyof MsEdit>(m: Milestone, k: K, orig: string | null): string => (msEdits[m.id]?.[k] ?? orig ?? '') as string;
  const addMs = () => act(async () => {
    const r = await api.post<Milestone>(`/projects/${project.id}/milestones`, { name: msName });
    if (r.similarNames?.length) toast('ok', `비슷한 이름이 있습니다: ${r.similarNames.join(', ')} (자동으로 합치지 않았습니다)`);
    setMsName('');
  }, '마일스톤을 추가했습니다.');

  return (
    <div className="stack">
      <div className="card">
        <div className="row between">
          <h3>기본 정보</h3>
          <span className={dirty ? 'save-state warn' : 'hint'}>{dirty ? '저장하지 않은 변경이 있습니다' : '변경 사항 없음'}</span>
        </div>
        <div className="row">
          <Field label="프로젝트명 (필수)"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="담당 팀 (필수)">
            <select value={form.teamId} onChange={(e) => setForm({ ...form, teamId: e.target.value, ownerUserId: ownerAfterTeamChange(users, form.ownerUserId, e.target.value, otherTeams) })}>
              {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </Field>
          <Field label="상태">
            <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
              {['preparing', 'in_progress', 'on_hold', 'completed', 'cancelled'].map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
            </select>
          </Field>
          <Field label="시작일"><input type="date" value={form.startDate} onChange={(e) => setForm({ ...form, startDate: e.target.value })} /></Field>
          <Field label={form.isShortTerm ? '마감일' : '종료일'} error={dateError}><input type="date" value={form.endDate} onChange={(e) => setForm({ ...form, endDate: e.target.value })} /></Field>
        </div>
        <div className="row">
          <Field label="대표 담당자 (필수)" hint={otherTeams ? undefined : '선택한 담당 팀의 구성원만 보입니다.'}>
            <select value={form.ownerUserId} onChange={(e) => setForm({ ...form, ownerUserId: e.target.value, memberIds: [...new Set([...form.memberIds, e.target.value])].filter(Boolean).sort() })}>
              <option value="">선택…</option>
              {candidateUsers(users, form.teamId, otherTeams, [form.ownerUserId]).map((u) => <option key={u.id} value={u.id}>{u.name}{u.teamName ? ` · ${u.teamName}` : ''}</option>)}
            </select>
          </Field>
          <Field label="참여자 (Ctrl/Shift 로 여러 명 선택, 대표는 항상 포함)">
            <select multiple size={Math.min(6, Math.max(3, users.length))} value={form.memberIds}
              onChange={(e) => setForm({ ...form, memberIds: [...new Set([...[...e.target.selectedOptions].map((o) => o.value), form.ownerUserId])].filter(Boolean).sort() })}>
              {candidateUsers(users, form.teamId, otherTeams, form.memberIds).map((u) => <option key={u.id} value={u.id}>{u.name}{u.teamName ? ` · ${u.teamName}` : ''}</option>)}
            </select>
          </Field>
          <label className="check"><input type="checkbox" checked={otherTeams} onChange={(e) => setOtherTeams(e.target.checked)} /> 다른 팀 구성원도 표시</label>
          <label className="check"><input type="checkbox" checked={form.isShortTerm} onChange={(e) => setForm({ ...form, isShortTerm: e.target.checked })} /> 단발성 프로젝트 (상세 입력 숨김, 값은 삭제되지 않음)</label>
        </div>
        <div className="row end">
          <button type="button" disabled={!dirty || busy} onClick={() => setForm(base)}>되돌리기</button>
          <button type="button" className="primary" disabled={!dirty || busy || !form.name.trim() || !form.teamId || !form.ownerUserId || !!dateError}
            onClick={async () => { if (await saveBasic()) setShowDetail(!form.isShortTerm); }}>저장</button>
        </div>
      </div>

      {project.isShortTerm && !showDetail && (
        <div className="card muted-card">
          <button type="button" onClick={() => setShowDetail(true)}>상세 입력 펼치기</button>{' '}
          {detail?.background && <span className="badge">배경 입력됨</span>} {detail?.purpose && <span className="badge">목적 입력됨</span>} {detail?.kpis && <span className="badge">KPI 입력됨</span>} {detail?.milestones && <span className="badge">마일스톤 입력됨</span>}
        </div>
      )}

      {showDetail && (
        <>
          <div className="card">
            <h3>배경 · 목적</h3>
            <Field label="배경"><RichEditor docKey={`bg-${project.id}-${project.revision}`} value={bg ?? project.backgroundDoc ?? emptyDocument()} images={null} onChange={setBg} /></Field>
            <Field label="목적"><RichEditor docKey={`pp-${project.id}-${project.revision}`} value={purpose ?? project.purposeDoc ?? emptyDocument()} images={null} onChange={setPurpose} /></Field>
            <div className="row end">
              <span className={textDirty ? 'save-state warn' : 'hint'}>{textDirty ? '저장하지 않은 변경이 있습니다' : ''}</span>
              <button type="button" className="primary" disabled={busy || !textDirty}
                onClick={async () => { if (await act(() => api.patch(`/projects/${project.id}`, { expectedRevision: project.revision, ...(bgDirty ? { backgroundDoc: bg } : {}), ...(purposeDirty ? { purposeDoc: purpose } : {}) }), '배경·목적을 저장했습니다.')) { setBg(null); setPurpose(null); } }}>저장</button>
            </div>
          </div>

          <div className="card">
            <h3>마일스톤</h3>
            <div className="row">
              <Field label="빠른 추가 (이름만 필수)"><input value={msName} onChange={(e) => setMsName(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && msName.trim()) void addMs(); }} /></Field>
              <button type="button" className="primary" disabled={!msName.trim() || busy} onClick={() => void addMs()}>추가</button>
              <Field label="간트 보기"><select value={view} onChange={(e) => setView(e.target.value as GanttViewMode)}><option value="Day">일</option><option value="Week">주</option><option value="Month">월</option></select></Field>
            </div>
            <MilestoneGantt milestones={ms} viewMode={view} onPlanChange={(m, s, e) => void patchMs(m, { plannedStart: s, plannedEnd: e })} />
            <p className="hint">간트 막대를 끌면 <strong>현재 계획이 바로 저장</strong>됩니다. 확정한 기준 일정과 실제일은 자동으로 바뀌지 않습니다. 표에서 고친 값은 행의 <strong>저장</strong>을 눌러야 반영됩니다.</p>
            <table className="grid">
              <thead><tr><th>마일스톤</th><th>상태</th><th>계획 시작</th><th>계획 종료</th><th>기준(확정)</th><th>실제 시작</th><th>실제 종료</th><th /></tr></thead>
              <tbody>
                {ms.map((m) => {
                  const changed = !!msEdits[m.id] && Object.keys(msEdits[m.id]).length > 0;
                  const ps = val(m, 'plannedStart', m.plannedStart), pe = val(m, 'plannedEnd', m.plannedEnd);
                  const bad = !!ps && !!pe && pe < ps;
                  return (
                    <tr key={m.id} className={changed ? 'bad-soft' : ''}>
                      <td>{m.isGeneral ? <>{m.name}<span className="badge">일반</span></> : <input value={val(m, 'name', m.name)} onChange={(e) => setE(m, { name: e.target.value })} />}</td>
                      <td>{m.isGeneral ? '—' : (
                        <select value={val(m, 'status', m.status)} onChange={(e) => setE(m, { status: e.target.value })}>
                          {['planned', 'in_progress', 'on_hold', 'completed', 'cancelled'].map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
                        </select>)}</td>
                      {m.isGeneral ? <td colSpan={5} className="hint">일정·완료율에 포함되지 않습니다.</td> : (
                        <>
                          <td><input type="date" value={ps} onChange={(e) => setE(m, { plannedStart: e.target.value })} /></td>
                          <td><input type="date" value={pe} onChange={(e) => setE(m, { plannedEnd: e.target.value })} />{bad && <small className="field-error"> 종료가 시작보다 빠름</small>}</td>
                          <td>{m.baselineStart ? `${m.baselineStart} ~ ${m.baselineEnd}` : '미확정'}</td>
                          <td><input type="date" value={val(m, 'actualStart', m.actualStart)} onChange={(e) => setE(m, { actualStart: e.target.value })} /></td>
                          <td><input type="date" value={val(m, 'actualEnd', m.actualEnd)} onChange={(e) => setE(m, { actualEnd: e.target.value })} /></td>
                        </>
                      )}
                      <td className="nowrap">
                        {!m.isGeneral && <button type="button" className="primary" disabled={!changed || busy || bad || !val(m, 'name', m.name).trim()} onClick={() => void saveMs(m)}>저장</button>}
                        {changed && <button type="button" onClick={() => setMsEdits(({ [m.id]: _d, ...r }) => r)}>취소</button>}
                        {!m.isGeneral && <button type="button" disabled={changed || !m.plannedStart || !m.plannedEnd} title={changed ? '먼저 저장하세요' : '현재 계획을 기준 일정으로 확정합니다'}
                          onClick={() => { if (!m.baselineStart || window.confirm('기준 일정을 현재 계획으로 다시 확정할까요? 이전 기준은 변경 이력에 남습니다.')) void act(() => api.post(`/milestones/${m.id}/confirm-baseline`, { expectedRevision: m.revision }), '기준 일정을 확정했습니다.'); }}>
                          {m.baselineStart ? '기준 재확정' : '기준 확정'}</button>}
                        {!m.isGeneral && <button type="button" onClick={() => { if (window.confirm(`'${m.name}' 마일스톤을 휴지통으로 보낼까요? 기존 일지 기록은 유지됩니다.`)) void act(() => api.del(`/milestones/${m.id}?expectedRevision=${m.revision}`), '휴지통으로 이동했습니다.'); }}>삭제</button>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="card">
            <h3>KPI (선택)</h3>
            <p className="hint">정량 성과에서 선택적으로 연결합니다. 성과 저장이 KPI 실적을 자동으로 덮어쓰거나 합산하지 않습니다.</p>
            <table className="grid">
              <thead><tr><th>이름</th><th>단위</th><th>기준값</th><th>목표값</th><th>방향</th><th /></tr></thead>
              <tbody>
                {kpis.map((k: Kpi) => (
                  <tr key={k.id} className={k.active ? '' : 'muted'}>
                    <td>{k.name}</td><td>{k.unit ?? '—'}</td><td>{k.baselineValue ?? '—'}</td><td>{k.targetValue ?? '—'}</td>
                    <td>{{ increase: '증가가 좋음', decrease: '감소가 좋음', target: '목표 맞춤' }[k.direction ?? ''] ?? '—'}</td>
                    <td><button type="button" onClick={() => void act(() => api.patch(`/kpis/${k.id}`, { expectedRevision: k.revision, active: !k.active }))}>{k.active ? '비활성화' : '활성화'}</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="row">
              <Field label="KPI 이름"><input value={kpi.name} onChange={(e) => setKpi({ ...kpi, name: e.target.value })} /></Field>
              <Field label="단위"><input value={kpi.unit} onChange={(e) => setKpi({ ...kpi, unit: e.target.value })} /></Field>
              <Field label="기준값"><input value={kpi.baselineValue} onChange={(e) => setKpi({ ...kpi, baselineValue: e.target.value })} /></Field>
              <Field label="목표값"><input value={kpi.targetValue} onChange={(e) => setKpi({ ...kpi, targetValue: e.target.value })} /></Field>
              <Field label="좋은 방향"><select value={kpi.direction} onChange={(e) => setKpi({ ...kpi, direction: e.target.value })}><option value="">미지정</option><option value="increase">증가</option><option value="decrease">감소</option><option value="target">목표 맞춤</option></select></Field>
              <button type="button" className="primary" disabled={!kpi.name.trim() || busy} onClick={() => void act(async () => {
                await api.post(`/projects/${project.id}/kpis`, { name: kpi.name, unit: kpi.unit || null, baselineValue: kpi.baselineValue || null, targetValue: kpi.targetValue || null, direction: kpi.direction || null });
                setKpi({ name: '', unit: '', baselineValue: '', targetValue: '', direction: '' });
              }, 'KPI를 추가했습니다.')}>KPI 추가</button>
            </div>
          </div>
        </>
      )}

      <div className="card">
        <h3>프로젝트 관리</h3>
        <p className="hint">복사는 프로젝트 목록의 ‘복사’ 버튼이나 ‘새 프로젝트’ 창에서 할 수 있습니다.</p>
        <button type="button" className="danger" onClick={() => { if (window.confirm(`'${project.name}' 프로젝트를 휴지통으로 보낼까요? 하위 기록은 그대로 보존되며 복원할 수 있습니다.`)) void act(async () => { await api.del(`/projects/${project.id}?expectedRevision=${project.revision}`); window.location.hash = '#/projects'; }, '휴지통으로 이동했습니다.'); }}>휴지통으로 이동</button>
      </div>
    </div>
  );
}
