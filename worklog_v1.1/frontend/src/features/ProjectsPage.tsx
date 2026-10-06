import { useEffect, useState } from 'react';
import { api, qs } from '../api/client';
import type { List, Org, Project } from '../api/types';
import { Field, Modal, STATUS_LABEL, errText, fmtDate, useAsync, useSession, useToast } from '../ui';
import { ApplyButtons, onEnter, useDraft } from './ProjectPicker';
import { ProjectInfo } from './ProjectInfo';
import { candidateUsers, ownerAfterTeamChange } from './teamUsers';

const FILTER_KEY = 'worklog.projectFilters';
interface Filters { divisionId: string; teamId: string; ownerId: string; status: string; q: string }
const EMPTY: Filters = { divisionId: '', teamId: '', ownerId: '', status: '', q: '' };

function loadFilters(): Filters {
  try { return { ...EMPTY, ...(JSON.parse(localStorage.getItem(FILTER_KEY) ?? '{}') as Partial<Filters>) }; } catch { return EMPTY; }
}

export function ProjectsPage() {
  const { users } = useSession();
  const [f, setF] = useState<Filters>(loadFilters); // 적용된 필터(목록 조회에 쓰임)
  useEffect(() => { try { localStorage.setItem(FILTER_KEY, JSON.stringify(f)); } catch { /* 필터 기억 실패는 무시 */ } }, [f]);
  const { draft, setDraft, dirty, apply } = useDraft(f, setF); // 입력 중인 값: ‘필터 적용’을 눌러야 f 로 반영
  const orgs = useAsync(() => api.get<List<Org>>('/organizations?limit=200'), []);
  const projects = useAsync(() => api.get<List<Project>>(`/projects${qs({ ...f, limit: 100 })}`), [f]);
  const [creating, setCreating] = useState(false);
  const [copyFrom, setCopyFrom] = useState('');
  const divisions = (orgs.data?.items ?? []).filter((o) => o.kind === 'division');
  const teams = (orgs.data?.items ?? []).filter((o) => o.kind === 'team' && (!draft.divisionId || o.parentId === draft.divisionId));
  return (
    <section>
      <div className="row between">
        <h2>프로젝트</h2>
        <button type="button" className="primary" onClick={() => { setCopyFrom(''); setCreating(true); }}>+ 새 프로젝트</button>
      </div>
      <div className="row filters">
        <Field label="담당 조직"><select value={draft.divisionId} onChange={(e) => setDraft({ ...draft, divisionId: e.target.value, teamId: '' })}><option value="">전체</option>{divisions.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></Field>
        <Field label="팀"><select value={draft.teamId} onChange={(e) => setDraft({ ...draft, teamId: e.target.value })}><option value="">전체</option>{teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
        <Field label="대표 담당자"><select value={draft.ownerId} onChange={(e) => setDraft({ ...draft, ownerId: e.target.value })}><option value="">전체</option>{users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></Field>
        <Field label="상태"><select value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value })}><option value="">전체</option>{Object.entries(STATUS_LABEL).filter(([k]) => ['preparing', 'in_progress', 'on_hold', 'completed', 'cancelled'].includes(k)).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
        <Field label="프로젝트명 검색"><input value={draft.q} onChange={(e) => setDraft({ ...draft, q: e.target.value })} onKeyDown={onEnter(apply)} placeholder="Enter로 적용" /></Field>
        <ApplyButtons dirty={dirty} onApply={apply} onReset={() => { setDraft(EMPTY); setF(EMPTY); }} />
      </div>
      {projects.error && <p className="field-error">{projects.error}</p>}
      <table className="grid clickable">
        <thead><tr><th>프로젝트</th><th>담당 조직 / 팀</th><th>대표</th><th>상태</th><th>기간</th><th /></tr></thead>
        <tbody>
          {(projects.data?.items ?? []).map((p) => (
            <tr key={p.id} onClick={() => { window.location.hash = `#/projects/${p.id}`; }} tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter') window.location.hash = `#/projects/${p.id}`; }}>
              <td><a href={`#/projects/${p.id}`}>{p.name}</a>{p.isShortTerm && <span className="badge">단발성</span>}</td>
              <td>{p.divisionName ? `${p.divisionName} / ` : ''}{p.teamName}</td><td>{p.ownerName}</td><td>{STATUS_LABEL[p.status]}</td>
              <td>{p.startDate || p.endDate ? `${fmtDate(p.startDate)} ~ ${fmtDate(p.endDate)}` : '—'}</td>
              <td className="nowrap"><button type="button" title="기준정보를 복사해 새 프로젝트 만들기" onClick={(e) => { e.stopPropagation(); setCopyFrom(p.id); setCreating(true); }}>복사</button></td>
            </tr>
          ))}
          {projects.data && projects.data.items.length === 0 && <tr><td colSpan={6} className="hint">조건에 맞는 프로젝트가 없습니다.</td></tr>}
        </tbody>
      </table>
      {creating && <CreateProject key={copyFrom} teams={(orgs.data?.items ?? []).filter((o) => o.kind === 'team' && o.active)} projects={projects.data?.items ?? []} copyFromId={copyFrom} onClose={() => setCreating(false)} />}
    </section>
  );
}

function CreateProject({ teams, projects, copyFromId, onClose }: { teams: Org[]; projects: Project[]; copyFromId: string; onClose: () => void }) {
  const toast = useToast();
  const { users, actor } = useSession();
  const [sourceId, setSourceId] = useState(copyFromId);
  const [copyMs, setCopyMs] = useState(true);
  const [copyKpi, setCopyKpi] = useState(true);
  const [otherTeams, setOtherTeams] = useState(false);
  const src = projects.find((p) => p.id === sourceId);
  const [form, setForm] = useState(() => {
    const s = projects.find((p) => p.id === copyFromId);
    return { name: s ? `${s.name} (복사)` : '', teamId: s?.teamId ?? actor?.teamId ?? '', ownerUserId: s?.ownerUserId ?? actor?.id ?? '', isShortTerm: s?.isShortTerm ?? false, endDate: '', startDate: '' };
  });
  const [busy, setBusy] = useState(false);
  const dateError = form.startDate && form.endDate && form.endDate < form.startDate ? '종료일은 시작일보다 빠를 수 없습니다.' : '';
  const ok = form.name.trim() && form.teamId && form.ownerUserId && !dateError;
  const pickSource = (id: string) => {
    setSourceId(id);
    const s = projects.find((p) => p.id === id);
    if (s) setForm((f) => ({ ...f, name: f.name.trim() ? f.name : `${s.name} (복사)`, teamId: s.teamId, ownerUserId: s.ownerUserId, isShortTerm: s.isShortTerm }));
  };
  const submit = async () => {
    setBusy(true);
    try {
      let p: Project;
      if (sourceId) {
        // 복사: 기준정보만 새 ID 로 재사용(일지·트래커·실적·이력·첨부·기간은 복사하지 않음). 팀/대표/기간은 이 창의 값으로 바로잡는다.
        p = await api.post<Project>(`/projects/${sourceId}/copy`, { name: form.name.trim(), copyMilestones: copyMs, copyKpis: copyKpi });
        const body: Record<string, unknown> = {};
        if (form.teamId !== p.teamId) body.teamId = form.teamId;
        if (form.ownerUserId !== p.ownerUserId) body.ownerUserId = form.ownerUserId;
        if (form.isShortTerm !== p.isShortTerm) body.isShortTerm = form.isShortTerm;
        if (form.startDate) body.startDate = form.startDate;
        if (form.endDate) body.endDate = form.endDate;
        if (Object.keys(body).length) p = await api.patch<Project>(`/projects/${p.id}`, { expectedRevision: p.revision, ...body });
      } else {
        p = await api.post<Project>('/projects', {
          name: form.name.trim(), teamId: form.teamId, ownerUserId: form.ownerUserId, isShortTerm: form.isShortTerm,
          startDate: form.startDate || null, endDate: form.endDate || null, memberIds: actor ? [actor.id] : [],
        });
      }
      toast('ok', sourceId ? '복사해서 새 프로젝트를 만들었습니다. 일지·트래커·실적·첨부는 복사하지 않았습니다.' : '프로젝트를 만들었습니다. ‘일반·수시 업무’ 마일스톤이 자동으로 생성되었습니다.');
      onClose();
      window.location.hash = `#/projects/${p.id}`;
    } catch (e) { toast('err', errText(e)); } finally { setBusy(false); }
  };
  return (
    <Modal title={sourceId ? '프로젝트 복사' : '새 프로젝트'} onClose={onClose}>
      <Field label="복사할 기존 프로젝트 (선택)" hint="고르면 기준정보(담당·마일스톤·KPI·배경/목적)를 새 프로젝트로 가져옵니다.">
        <select value={sourceId} onChange={(e) => pickSource(e.target.value)}>
          <option value="">복사하지 않고 새로 만들기</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.teamName}</option>)}
        </select>
      </Field>
      {src && (
        <div className="sub-card">
          <label className="check"><input type="checkbox" checked={copyMs} onChange={(e) => setCopyMs(e.target.checked)} /> 마일스톤 정의 복사 (이름·설명만, 일정은 제외)</label>{' '}
          <label className="check"><input type="checkbox" checked={copyKpi} onChange={(e) => setCopyKpi(e.target.checked)} /> KPI 정의 복사</label>
          <p className="hint">일지, To-Do/Issue, 성과, 첨부, 변경 이력, 일정은 복사하지 않습니다. 상태는 ‘준비’로 시작합니다.</p>
        </div>
      )}
      <Field label="프로젝트명 (필수)"><input autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
      <Field label="담당 팀 (필수)"><select value={form.teamId} onChange={(e) => setForm({ ...form, teamId: e.target.value, ownerUserId: ownerAfterTeamChange(users, form.ownerUserId, e.target.value, otherTeams) })}><option value="">선택…</option>{teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
      <Field label="대표 담당자 (필수)" hint={form.teamId ? '선택한 담당 팀의 구성원만 보입니다. 일지 작성자와 달라도 됩니다.' : '담당 팀을 먼저 선택하세요.'}>
        <select value={form.ownerUserId} disabled={!form.teamId && !otherTeams} onChange={(e) => setForm({ ...form, ownerUserId: e.target.value })}>
          <option value="">{form.teamId || otherTeams ? '선택…' : '담당 팀을 먼저 선택'}</option>
          {candidateUsers(users, form.teamId, otherTeams, form.ownerUserId ? [form.ownerUserId] : []).map((u) => <option key={u.id} value={u.id}>{u.name}{u.teamName ? ` · ${u.teamName}` : ''}</option>)}
        </select>
      </Field>
      <label className="check"><input type="checkbox" checked={otherTeams} onChange={(e) => setOtherTeams(e.target.checked)} /> 다른 팀 구성원도 대표로 선택 가능</label>

      <label className="check"><input type="checkbox" checked={form.isShortTerm} onChange={(e) => setForm({ ...form, isShortTerm: e.target.checked })} /> 단발성 프로젝트 (마감일 중심, 상세 입력은 접어 둠)</label>
      <div className="row">
        {!form.isShortTerm && <Field label="시작일"><input type="date" value={form.startDate} onChange={(e) => setForm({ ...form, startDate: e.target.value })} /></Field>}
        <Field label={form.isShortTerm ? '마감일' : '종료일'} error={dateError}><input type="date" value={form.endDate} onChange={(e) => setForm({ ...form, endDate: e.target.value })} /></Field>
      </div>
      <p className="hint">참여자·배경·KPI는 만든 뒤 프로젝트 기준정보에서 입력하고 <strong>저장</strong>할 수 있습니다.</p>
      <div className="row end"><button type="button" onClick={onClose}>취소</button><button type="button" className="primary" disabled={!ok || busy} onClick={() => void submit()}>{sourceId ? '복사해서 만들기' : '만들기'}</button></div>
    </Modal>
  );
}
/** 프로젝트 탭 = 기준정보 화면(조직·사용자 탭과 같은 성격). 일지/To-Do/Issue 는 각자의 탭에서 작성한다. */
export function ProjectDetail({ projectId }: { projectId: string }) {
  const { data: project, error, reload } = useAsync(() => api.get<Project>(`/projects/${projectId}`), [projectId]);
  if (error) return <p className="field-error">{error} <a href="#/projects">목록으로</a></p>;
  if (!project) return <p className="hint">불러오는 중…</p>;
  return (
    <section>
      <p className="crumb"><a href="#/projects">프로젝트</a> › {project.name}</p>
      <div className="row between">
        <h2>{project.name}{project.isShortTerm && <span className="badge">단발성</span>}</h2>
        <span className="hint">
          기록하러 가기: <a href={`#/logs/${project.id}`}>업무일지</a> · <a href={`#/todos/${project.id}`}>To-Do</a> · <a href={`#/issues/${project.id}`}>Issue</a>
        </span>
      </div>
      <ProjectInfo project={project} reload={reload} />
    </section>
  );
}