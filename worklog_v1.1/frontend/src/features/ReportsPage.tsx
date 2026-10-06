import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api/client';
import type { List, Project } from '../api/types';
import { Field, STATUS_LABEL, errText, todayLocal, useAsync, useSession, useToast } from '../ui';
import { ApplyButtons, FilterBar, useDraft } from './ProjectPicker';
import { defaultFilters, filterProjects, type PickerFilters } from './projectFilter';
import { daysBetween, isoWeekOf, monthWeeks, shortDay, weekLabel } from './reportDates';
import { addDays } from '../gantt/adapter';

type Kind = 'weekly' | 'period' | 'monthly';
export type Template = 'weekly' | 'exec';

interface ReportConfig { aiMode: 'live' | 'paste'; aiModel: string | null; aiPasteReason?: string; aiUrlConfigured: boolean; aiKeyConfigured: boolean; fonts: boolean; maxProjects: number }
interface JobFile { name: string; label: string; sizeBytes: number }
interface Need { promptId: string; promptLabel: string; responseName: string; projectId: string; projectName: string | null; prompt?: string; format: string }
interface Job {
  id: string; kind: Kind; kindLabel: string; template: string; templateLabel: string; periodLabel: string; projectIds: string[]; projectNames: string[];
  status: 'queued' | 'running' | 'need_response' | 'succeeded' | 'failed' | 'cancelled'; stage: string; need: Need | null;
  result: { files: JobFile[]; slideCount: number; problems: string[] } | null; error: string | null; responsesReceived: number;
  requestedBy: { id: string; name: string }; createdAt: string; aiMode: 'live' | 'paste';
  options: { includeTables: boolean; includeGantts: boolean; includeMilestoneGantt: boolean; refreshAi: boolean;
    includeTeamSummary?: boolean; summaryAuthor?: string | null };
}

const STATE: Record<Job['status'], string> = {
  queued: '대기 중', running: '만드는 중', need_response: 'AI 응답 필요', succeeded: '완료', failed: '실패', cancelled: '취소됨',
};
const ACTIVE = new Set(['queued', 'running']);
const fileUrl = (job: Job, f: JobFile) => `/api/v1/reports/jobs/${job.id}/files/${encodeURIComponent(f.name)}`;
const fmtTime = (iso: string) => new Date(iso).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });

async function copyText(text: string, area?: HTMLTextAreaElement | null): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    if (!area) return false; // http(사내 주소)에서는 clipboard API가 막힐 수 있어 선택 후 복사로 대신한다
    area.focus();
    area.select();
    return document.execCommand('copy');
  }
}

/** initialProjectIds·initialTemplate: 왼쪽 트리의 PJT ▸ 자료 생성기(#/reports?project=<id>&template=weekly|exec)에서 미리 고른 값 */
export function ReportsPage({ initialProjectIds, initialTemplate }: { initialProjectIds?: string[]; initialTemplate?: Template } = {}) {
  const config = useAsync(() => api.get<ReportConfig>('/reports/config'), []);
  const jobs = useAsync(() => api.get<{ items: Job[] }>('/reports/jobs?limit=30'), []);
  const [activeId, setActiveId] = useState<string | null>(null);
  const cfg = config.data;
  return (
    <section className="stack">
      <h2>보고자료</h2>
      {config.error && <div className="notice warn" role="alert">{config.error}</div>}
      {cfg && (cfg.aiMode === 'live'
        ? <div className="notice">AI: 서버에 연결된 AI{cfg.aiModel ? `(${cfg.aiModel})` : ''}로 바로 정리합니다. 과제 수에 따라 몇 분 걸릴 수 있으며, 다른 화면으로 가도 서버에서 계속 만듭니다.</div>
        : <div className="notice warn">
            AI: 서버에 AI 연결이 설정되지 않아 <strong>붙여넣기 방식</strong>으로 만듭니다. 만드는 도중 ‘AI 응답 필요’가 나오면 프롬프트를 복사해 사내 AI에 보내고, 받은 JSON을 붙여 넣으세요(과제마다 2~3번, 팀장 요약 페이지를 넣으면 1번 더).
            {' '}관리자는 <code>config\config.json</code>의 <code>AI_API_URL</code>·<code>AI_API_KEY</code>를 넣고 <strong>서버를 다시 시작</strong>하면 모든 사용자에게 서버 연결이 켜집니다.
            {cfg.aiPasteReason && <><br /><span className="hint">서버가 읽은 설정: {cfg.aiPasteReason}</span></>}
          </div>)}
      {cfg && !cfg.fonts && <p className="hint">서버에 LG스마트체 글꼴 파일이 없어 줄 수를 보수적으로 계산합니다(내용이 조금 덜 담길 수 있음).</p>}
      <CreateForm config={cfg} initialProjectIds={initialProjectIds} initialTemplate={initialTemplate} onCreated={(id) => { setActiveId(id); jobs.reload(); }} />
      {activeId && <JobPanel key={activeId} id={activeId} onChange={jobs.reload} onClose={() => setActiveId(null)} />}
      <History jobs={jobs.data?.items ?? []} activeId={activeId} onOpen={setActiveId} onReload={jobs.reload} />
    </section>
  );
}

// ── 만들기 ───────────────────────────────────────────────────────────────────

function CreateForm({ config, onCreated, initialProjectIds, initialTemplate }: {
  config: ReportConfig | null; onCreated: (id: string) => void; initialProjectIds?: string[]; initialTemplate?: Template;
}) {
  const toast = useToast();
  const { actor } = useSession();
  const projects = useAsync(() => api.get<List<Project>>('/projects?limit=200'), []);
  const all = useMemo(() => projects.data?.items ?? [], [projects.data]);
  const today = todayLocal();
  const [kind, setKind] = useState<Kind>('weekly');
  const [template, setTemplate] = useState<Template>(initialTemplate ?? 'weekly');
  const [baseDate, setBaseDate] = useState(today);
  const [from, setFrom] = useState(addDays(today, -27));
  const [to, setTo] = useState(today);
  const [month, setMonth] = useState(today.slice(0, 7));
  // 과제를 미리 골라 왔으면 그 과제가 보이도록 상태 필터를 풀어 둔다 (완료 과제도 보고자료를 만들 수 있게)
  const [filters, setFilters] = useState<PickerFilters>(() => ({ ...defaultFilters(false), status: initialProjectIds?.length ? '' : 'in_progress' }));
  const { draft, setDraft, dirty, apply } = useDraft(filters, setFilters);
  const [selected, setSelected] = useState<string[]>(initialProjectIds ?? []);
  const [opts, setOpts] = useState({ includeTables: true, includeGantts: true, includeMilestoneGantt: true, refreshAi: false });
  // 팀장 요약 페이지 (주간·기간 보고 + 주간업무 양식): 팀별 맨 앞에 AI 요약 1장
  const [teamSummary, setTeamSummary] = useState(true);
  const [summaryAuthor, setSummaryAuthor] = useState('');
  const [busy, setBusy] = useState(false);

  const shown = useMemo(() => filterProjects(all, filters, actor?.id ?? null), [all, filters, actor]);
  const shownIds = shown.map((p) => p.id);
  const allShownSelected = shown.length > 0 && shownIds.every((id) => selected.includes(id));
  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const selectedProjects = all.filter((p) => selected.includes(p.id));
  const single = selectedProjects.length === 1 ? selectedProjects[0] : null;
  const teamCount = new Set(selectedProjects.map((p) => p.teamId)).size;
  const max = config?.maxProjects ?? 30;

  const orgLabel = (() => {
    if (filters.teamId) return all.find((p) => p.teamId === filters.teamId)?.teamName ?? null;
    if (filters.divisionId) return all.find((p) => p.divisionId === filters.divisionId)?.divisionName ?? null;
    const teams = new Set(selectedProjects.map((p) => p.teamName));
    if (teams.size === 1) return selectedProjects[0]?.teamName ?? null;
    const divs = new Set(selectedProjects.map((p) => p.divisionName));
    return divs.size === 1 ? selectedProjects[0]?.divisionName ?? null : null;
  })();

  const week = isoWeekOf(baseDate);
  const monthInfo = month ? monthWeeks(month) : null;
  const periodError = kind === 'period' && (!from || !to ? '시작일과 마감일을 정하세요.' : to < from ? '마감일이 시작일보다 빠릅니다.' : daysBetween(from, to) > 366 ? '기간은 최대 366일입니다.' : null);
  const blocker = !actor ? '상단에서 작성자를 먼저 선택하세요.' : selected.length === 0 ? '프로젝트를 하나 이상 고르세요.'
    : selected.length > max ? `한 번에 최대 ${max}개까지 만들 수 있습니다.` : periodError || (kind === 'monthly' && !month ? '월을 고르세요.' : null);

  const submit = async () => {
    setBusy(true);
    try {
      const body: Record<string, unknown> = { kind, projectIds: selected, orgLabel, ...opts };
      if (kind !== 'monthly') body.template = template;
      if (kind !== 'monthly' && template === 'weekly') {
        body.includeTeamSummary = teamSummary;
        if (teamSummary && summaryAuthor.trim()) body.summaryAuthor = summaryAuthor.trim();
      }
      if (kind === 'weekly') body.week = week.week;
      if (kind === 'period') Object.assign(body, { dateFrom: from, dateTo: to });
      if (kind === 'monthly') body.month = month;
      const job = await api.post<Job>('/reports/jobs', body);
      toast('ok', '보고자료 만들기를 시작했습니다.');
      onCreated(job.id);
    } catch (e) { toast('err', errText(e)); } finally { setBusy(false); }
  };

  return (
    <div className="card stack">
      <h3>보고자료 만들기</h3>
      <div className="tabs" role="tablist">
        {(['weekly', 'period', 'monthly'] as Kind[]).map((k) => (
          <button key={k} type="button" role="tab" aria-selected={kind === k} className={kind === k ? 'active' : ''} onClick={() => setKind(k)}>
            {{ weekly: '주간 보고', period: '기간 보고', monthly: '월간 종합' }[k]}
          </button>
        ))}
      </div>

      <div className="row">
        {kind === 'weekly' && (
          <>
            <Field label="기준 일자 (그 날이 속한 주)"><input type="date" value={baseDate} onChange={(e) => e.target.value && setBaseDate(e.target.value)} /></Field>
            <div className="row inline">
              <button type="button" onClick={() => setBaseDate(addDays(week.start, -7))}>◀ 이전 주</button>
              <button type="button" onClick={() => setBaseDate(today)}>이번 주</button>
              <button type="button" onClick={() => setBaseDate(addDays(week.start, 7))}>다음 주 ▶</button>
            </div>
            <p className="report-range"><strong>{weekLabel(baseDate)}</strong><br /><small className="hint">ISO 주차(월~일) 기준으로 그 주 업무일지를 정리합니다.</small></p>
          </>
        )}
        {kind === 'period' && (
          <>
            <Field label="시작일"><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
            <Field label="마감일"><input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
            <div className="row inline">
              <button type="button" disabled={!single || !(single.startDate || single.endDate)}
                title={single ? undefined : '프로젝트를 하나만 골랐을 때 쓸 수 있습니다'}
                onClick={() => { if (single) { setFrom(single.startDate ?? single.endDate ?? from); setTo(single.endDate && single.endDate < today ? single.endDate : today); } }}>
                선택한 프로젝트 기간으로
              </button>
              <button type="button" onClick={() => { setFrom(`${today.slice(0, 7)}-01`); setTo(today); }}>이번 달</button>
              <button type="button" onClick={() => { setFrom(addDays(today, -27)); setTo(today); }}>최근 4주</button>
            </div>
            <p className="report-range">
              {periodError ? <span className="field-error">{periodError}</span>
                : <><strong>{shortDay(from)} ~ {shortDay(to)}</strong> ({daysBetween(from, to)}일)<br /><small className="hint">기간 안 업무일지를 한 번에 정리합니다.</small></>}
            </p>
          </>
        )}
        {kind === 'monthly' && (
          <>
            <Field label="월"><input type="month" value={month} onChange={(e) => setMonth(e.target.value)} /></Field>
            {monthInfo && <p className="report-range"><strong>{monthInfo.weeks[0]} ~ {monthInfo.weeks[monthInfo.weeks.length - 1]}</strong> ({shortDay(monthInfo.start)} ~ {shortDay(monthInfo.end)})<br />
              <small className="hint">목요일이 그 달에 있는 주를 모읍니다. 주간 정리가 없는 주는 먼저 정리합니다.</small></p>}
          </>
        )}
      </div>

      {kind !== 'monthly' && (
        <fieldset className="report-templates">
          <legend>양식</legend>
          <label className="check"><input type="radio" name="tpl" checked={template === 'weekly'} onChange={() => setTemplate('weekly')} /> 주간업무 양식 <small className="hint">(과제당 1~2장: 마일스톤 표·누적 요약·진행·계획·이슈)</small></label>
          <label className="check"><input type="radio" name="tpl" checked={template === 'exec'} onChange={() => setTemplate('exec')} /> 경영진 1장 요약 양식 <small className="hint">(과제당 1장: 헤드메시지·배경 및 결론·경과·계획)</small></label>
          {template === 'weekly' && (
            <div className="stack team-summary">
              <label className="check">
                <input type="checkbox" checked={teamSummary} onChange={(e) => setTeamSummary(e.target.checked)} /> 팀장 요약 페이지 포함
                <small className="hint">(팀별 맨 앞 1장: 과제마다 배경·진행·이슈·잘한점·계획을 AI가 요약, 이번 {kind === 'period' ? '기간' : '주'} 내용은 파란색)</small>
              </label>
              {teamSummary && (
                <label className="row inline">
                  작성자(팀장)
                  <input type="text" maxLength={40} value={summaryAuthor} onChange={(e) => setSummaryAuthor(e.target.value)}
                    placeholder="예: 홍길동 팀장 — 비우면 첫 과제 담당자" aria-label="팀장 요약 작성자" />
                </label>
              )}
              {teamSummary && teamCount > 1 && <small className="hint">선택한 프로젝트가 {teamCount}개 팀에 걸쳐 있어 팀마다 [요약 → 과제 장표] 순서로 넣습니다.</small>}
            </div>
          )}
        </fieldset>
      )}

      <div className="sub-card stack">
        <div className="row picker">
          <FilterBar projects={all} filters={draft} onChange={setDraft} onEnter={apply} />
          <ApplyButtons dirty={dirty} onApply={apply} onReset={() => { const f = { ...defaultFilters(!!actor), status: '' }; setDraft(f); setFilters(f); }} />
        </div>
        <div className="row between">
          <strong>프로젝트 선택 ({selected.length}개{selected.length > max ? ` — 최대 ${max}개` : ''})</strong>
          <span className="row inline">
            <button type="button" disabled={shown.length === 0} onClick={() => setSelected((s) => (allShownSelected ? s.filter((id) => !shownIds.includes(id)) : [...new Set([...s, ...shownIds])]))}>
              {allShownSelected ? '보이는 프로젝트 선택 해제' : `보이는 프로젝트 모두 선택 (${shown.length})`}
            </button>
            <button type="button" disabled={selected.length === 0} onClick={() => setSelected([])}>선택 비우기</button>
          </span>
        </div>
        <div className="project-checks" role="group" aria-label="프로젝트 선택">
          {projects.loading && <p className="hint">불러오는 중…</p>}
          {!projects.loading && shown.length === 0 && <p className="hint">필터에 맞는 프로젝트가 없습니다. 조건을 바꿔 ‘필터 적용’을 누르세요.</p>}
          {shown.map((p) => (
            <label key={p.id} className="check">
              <input type="checkbox" checked={selected.includes(p.id)} onChange={() => toggle(p.id)} />
              <span>{p.name}</span>
              <small className="hint">{p.divisionName ?? '—'} / {p.teamName ?? '—'} · {STATUS_LABEL[p.status] ?? p.status}{p.startDate || p.endDate ? ` · ${p.startDate ?? '?'} ~ ${p.endDate ?? '?'}` : ''}</small>
            </label>
          ))}
        </div>
        {selectedProjects.some((p) => !shownIds.includes(p.id)) && (
          <small className="hint">필터 밖에 선택된 프로젝트: {selectedProjects.filter((p) => !shownIds.includes(p.id)).map((p) => p.name).join(', ')}</small>
        )}
      </div>

      <fieldset className="report-templates">
        <legend>참고 슬라이드 (PPT 표·도형으로 넣어 받은 사람이 고칠 수 있음)</legend>
        <label className="check"><input type="checkbox" checked={opts.includeTables} onChange={(e) => setOpts({ ...opts, includeTables: e.target.checked })} /> 업무일지의 표</label>
        <label className="check"><input type="checkbox" checked={opts.includeGantts} onChange={(e) => setOpts({ ...opts, includeGantts: e.target.checked })} /> 업무일지의 간트 차트</label>
        <label className="check"><input type="checkbox" checked={opts.includeMilestoneGantt} onChange={(e) => setOpts({ ...opts, includeMilestoneGantt: e.target.checked })} /> 프로젝트 마일스톤 일정(간트)</label>
        <label className="check"><input type="checkbox" checked={opts.refreshAi} onChange={(e) => setOpts({ ...opts, refreshAi: e.target.checked })} /> AI 정리 새로 받기 <small className="hint">(끄면 같은 입력의 이전 정리 결과를 다시 씁니다. 업무일지가 바뀌면 자동으로 새로 받습니다.)</small></label>
      </fieldset>

      <div className="row">
        <button type="button" className="primary" disabled={!!blocker || busy} onClick={() => void submit()}>PPT 만들기</button>
        {blocker && <small className="hint">{blocker}</small>}
        {!blocker && orgLabel && kind === 'monthly' && <small className="hint">제목 조직: {orgLabel}</small>}
      </div>
    </div>
  );
}

// ── 진행 상황 ─────────────────────────────────────────────────────────────────

function JobPanel({ id, onChange, onClose }: { id: string; onChange: () => void; onClose: () => void }) {
  const toast = useToast();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [answerError, setAnswerError] = useState<string | null>(null);
  // 팀장 요약 페이지 (주간·기간 보고 + 주간업무 양식): 팀별 맨 앞에 AI 요약 1장
  const [teamSummary, setTeamSummary] = useState(true);
  const [summaryAuthor, setSummaryAuthor] = useState('');
  const [busy, setBusy] = useState(false);
  const promptRef = useRef<HTMLTextAreaElement>(null);
  const lastStatus = useRef<string | null>(null);
  const [tick, setTick] = useState(0); // 응답 저장·다시 실행 뒤 상태 조회를 다시 시작

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const load = async () => {
      try {
        const j = await api.get<Job>(`/reports/jobs/${id}`);
        if (!alive) return;
        setJob(j);
        setError(null);
        if (lastStatus.current !== j.status) { lastStatus.current = j.status; onChange(); }
        if (ACTIVE.has(j.status)) timer = window.setTimeout(() => void load(), 1500);
      } catch (e) {
        if (alive) { setError(errText(e)); timer = window.setTimeout(() => void load(), 4000); }
      }
    };
    void load();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [id, tick]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = async () => setJob(await api.get<Job>(`/reports/jobs/${id}`));
  const sendAnswer = async () => {
    if (!job?.need) return;
    setBusy(true);
    setAnswerError(null);
    try {
      const j = await api.post<Job>(`/reports/jobs/${id}/response`, { responseName: job.need.responseName, text });
      setText('');
      setJob(j);
      setTick((t) => t + 1);
    } catch (e) { setAnswerError(errText(e)); } finally { setBusy(false); }
  };
  const act = async (path: 'retry' | 'cancel') => {
    try { setJob(await api.post<Job>(`/reports/jobs/${id}/${path}`)); setTick((t) => t + 1); } catch (e) { toast('err', errText(e)); }
  };

  if (!job) return <div className="card">{error ? <p className="field-error">{error}</p> : <p className="hint">불러오는 중…</p>}</div>;
  const need = job.status === 'need_response' ? job.need : null;
  return (
    <div className="card stack" aria-live="polite">
      <div className="row between">
        <h3>{job.kindLabel} · {job.templateLabel}{job.options?.includeTeamSummary ? ' + 팀장 요약' : ''} <small className="hint">{job.periodLabel}</small></h3>
        <span className="row inline">
          {['queued', 'need_response', 'failed'].includes(job.status) && <button type="button" onClick={() => void act('cancel')}>작업 취소</button>}
          <button type="button" onClick={onClose}>닫기</button>
        </span>
      </div>
      <p>
        <span className={`badge${job.status === 'failed' ? ' bad' : ''}`}>{STATE[job.status]}</span> {job.stage}
        {ACTIVE.has(job.status) && <small className="hint"> (자동으로 새로고침합니다)</small>}
      </p>
      <small className="hint">프로젝트 {job.projectNames.length}개: {job.projectNames.join(', ')}</small>

      {need && (
        <div className="sub-card stack">
          <strong>AI 응답이 필요합니다 — {need.projectName ?? ''} · {need.promptLabel} {job.responsesReceived > 0 && <small className="hint">(지금까지 {job.responsesReceived}개 받음)</small>}</strong>
          <ol className="steps">
            <li>
              <button type="button" onClick={() => void copyText(need.prompt ?? '', promptRef.current).then((ok) => toast(ok ? 'ok' : 'err', ok ? '프롬프트를 복사했습니다.' : '복사하지 못했습니다. 아래 칸을 직접 선택해 복사하세요.'))}>프롬프트 복사</button>
              {' '}→ 사내 AI(EXAONE 등) 대화창에 붙여 넣어 보냅니다.
              <textarea ref={promptRef} className="mono" readOnly rows={6} value={need.prompt ?? ''} aria-label="AI에 보낼 프롬프트" />
            </li>
            <li>
              AI가 돌려준 JSON을 아래에 붙여 넣고 ‘응답 저장 후 계속’을 누릅니다. <small className="hint">설명 문장이나 ```json 표시가 섞여 있어도 됩니다. 필요한 형식: <code>{need.format}</code></small>
              <textarea className="mono" rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder={need.format} aria-label="AI 응답" />
              {answerError && <p className="field-error" role="alert">{answerError}</p>}
              <button type="button" className="primary" disabled={!text.trim() || busy} onClick={() => void sendAnswer()}>응답 저장 후 계속</button>
            </li>
          </ol>
        </div>
      )}

      {job.status === 'succeeded' && job.result && (
        <div className="stack">
          <p className="ok-text">PPT {job.result.slideCount}장을 만들었습니다.</p>
          <div className="row">
            {job.result.files.map((f) => <a key={f.name} className={`btn${f.label === 'PPT' ? ' primary' : ''}`} href={fileUrl(job, f)} download>{f.label} 내려받기</a>)}
          </div>
          {job.result.problems.length > 0 && (
            <details><summary>PPT 재검사 알림 {job.result.problems.length}건</summary><ul>{job.result.problems.map((p, i) => <li key={i}>{p}</li>)}</ul></details>
          )}
          <small className="hint">문장은 AI 정리 결과입니다. 숫자·날짜 근거 확인 결과는 검사 보고서에 있습니다. PowerPoint에서 열어 확인 후 사용하세요.</small>
        </div>
      )}
      {job.status === 'failed' && (
        <div className="stack">
          <p className="field-error" role="alert">{job.error}</p>
          <div className="row"><button type="button" onClick={() => void act('retry')}>다시 실행</button></div>
        </div>
      )}
      {job.status === 'cancelled' && <div className="row"><button type="button" onClick={() => void act('retry')}>다시 실행</button></div>}
      {error && <p className="field-error">{error} <button type="button" onClick={() => void refresh()}>다시 불러오기</button></p>}
    </div>
  );
}

// ── 최근 작업 ─────────────────────────────────────────────────────────────────

function History({ jobs, activeId, onOpen, onReload }: { jobs: Job[]; activeId: string | null; onOpen: (id: string) => void; onReload: () => void }) {
  return (
    <div className="card">
      <div className="row between"><h3>최근 보고자료</h3><button type="button" onClick={onReload}>새로고침</button></div>
      <p className="hint">모든 사용자가 만든 보고자료가 보입니다. 서버에 최근 작업이 보관되며 오래된 것부터 지워집니다.</p>
      {jobs.length === 0 ? <p className="hint">아직 만든 보고자료가 없습니다.</p> : (
        <table className="grid">
          <thead><tr><th>종류 · 양식</th><th>기간</th><th>프로젝트</th><th>요청</th><th>상태</th><th /></tr></thead>
          <tbody>{jobs.map((j) => {
            const ppt = j.result?.files.find((f) => f.label === 'PPT');
            return (
              <tr key={j.id} className={j.id === activeId ? 'sel' : j.status === 'failed' ? 'bad-soft' : ''}>
                <td>{j.kindLabel}<br /><small className="hint">{j.templateLabel}{j.options?.includeTeamSummary ? ' + 팀장 요약' : ''}</small></td>
                <td>{j.periodLabel}</td>
                <td>{j.projectNames[0]}{j.projectNames.length > 1 ? ` 외 ${j.projectNames.length - 1}개` : ''}</td>
                <td>{j.requestedBy?.name}<br /><small className="hint">{fmtTime(j.createdAt)}</small></td>
                <td>{STATE[j.status]}</td>
                <td className="nowrap">
                  <button type="button" onClick={() => onOpen(j.id)}>{j.status === 'need_response' ? '이어서 하기' : '열기'}</button>
                  {ppt && <> <a className="btn" href={fileUrl(j, ppt)} download>PPT</a></>}
                </td>
              </tr>
            );
          })}</tbody>
        </table>
      )}
    </div>
  );
}
