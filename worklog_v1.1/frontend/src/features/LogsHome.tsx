import { useEffect, useMemo, useState } from 'react';
import { api, qs } from '../api/client';
import type { List, Project } from '../api/types';
import { Field, Modal, STATUS_LABEL, errText, todayLocal, useAsync, useSession, useToast } from '../ui';
import { monthGrid, monthRange, shiftMonth } from './calendar';
import { LogView } from './LogView';
import { ProjectPicker, usePickerFilters } from './ProjectPicker';

interface LogRow {
  id: string; projectId: string; projectName: string; projectStatus: string; teamName: string | null; authorId: string;
  authorName: string | null; authorTeam: string | null; workDate: string; revision: number; updatedAt: string;
  tasks: { id: string; milestone: string | null; title: string | null; titlePreview: string; contentPreview: string; attachmentCount: number }[];
  todoCount: number; issueCount: number; achievementCount: number;
}
const WEEK = ['일', '월', '화', '수', '목', '금', '토'];
const AUTHOR_KEY = 'worklog.logAuthorScope';
const timeOf = (iso: string) => new Date(iso).toLocaleTimeString('ko-KR', { hour12: false, hour: '2-digit', minute: '2-digit' });

/** 업무일지 탭의 시작 화면: 왼쪽 달력, 오른쪽에 선택한 날의 일지 목록. 작성은 ‘업무일지 작성’에서 프로젝트를 고른 뒤 시작한다. */
export function LogsHome({ initialDate }: { initialDate?: string }) {
  const { actor } = useSession();
  const [date, setDate] = useState(initialDate || todayLocal());
  const [ym, setYm] = useState(() => { const d = initialDate || todayLocal(); return { year: Number(d.slice(0, 4)), month: Number(d.slice(5, 7)) }; });
  const [filters, setFilters] = usePickerFilters();
  const [projectId, setProjectId] = useState('');
  const [authorMe, setAuthorMe] = useState<boolean>(() => { try { return localStorage.getItem(AUTHOR_KEY) === 'me'; } catch { return false; } });
  useEffect(() => { try { localStorage.setItem(AUTHOR_KEY, authorMe ? 'me' : 'all'); } catch { /* 무시 */ } }, [authorMe]);
  const [creating, setCreating] = useState(false);
  const [viewId, setViewId] = useState<string | null>(null);

  const projects = useAsync(() => api.get<List<Project>>('/projects?limit=200'), []);
  const all = projects.data?.items ?? [];

  // 서버에 보내는 조회 조건: 달력과 목록이 같은 조건을 쓴다
  const q = useMemo(() => ({
    memberId: filters.scope === 'mine' && actor ? actor.id : '',
    divisionId: filters.divisionId, teamId: filters.teamId, status: filters.status, q: filters.q.trim(),
    projectId, authorId: authorMe && actor ? actor.id : '',
  }), [filters, projectId, authorMe, actor]);
  const qKey = JSON.stringify(q);
  const range = monthRange(ym.year, ym.month);
  const cal = useAsync(() => api.get<{ days: { date: string; count: number }[] }>(`/logs/calendar${qs({ dateFrom: range.from, dateTo: range.to, ...q })}`), [range.from, qKey]);
  const list = useAsync(() => api.get<List<LogRow>>(`/logs${qs({ dateFrom: date, dateTo: date, ...q })}`), [date, qKey]);
  const counts = useMemo(() => Object.fromEntries((cal.data?.days ?? []).map((d) => [d.date, d.count])), [cal.data]);
  const today = todayLocal();
  const grid = monthGrid(ym.year, ym.month);

  const pick = (d: string) => {
    setDate(d);
    if (Number(d.slice(5, 7)) !== ym.month) setYm({ year: Number(d.slice(0, 4)), month: Number(d.slice(5, 7)) });
    window.history.replaceState(null, '', `#/logs?date=${d}`);
  };
  const items = list.data?.items ?? [];

  return (
    <section>
      <div className="row between">
        <h2>업무일지</h2>
        <button type="button" className="primary" onClick={() => setCreating(true)}>+ 업무일지 작성</button>
      </div>

      <div className="row filters">
        <ProjectPicker projects={all} value={projectId} onChange={setProjectId} filters={filters} onFiltersChange={setFilters} allowAll label="프로젝트"
          author={{ me: authorMe, onChange: setAuthorMe }} />
      </div>

      <div className="logs-layout">
        <aside className="calendar card" aria-label="달력">
          <div className="cal-head">
            <button type="button" onClick={() => setYm(shiftMonth(ym.year, ym.month, -1))} aria-label="이전 달">‹</button>
            <strong>{ym.year}년 {ym.month}월</strong>
            <button type="button" onClick={() => setYm(shiftMonth(ym.year, ym.month, 1))} aria-label="다음 달">›</button>
            <button type="button" onClick={() => { pick(today); setYm({ year: Number(today.slice(0, 4)), month: Number(today.slice(5, 7)) }); }}>오늘</button>
          </div>
          <div className="cal-grid" role="grid">
            {WEEK.map((w, i) => <div key={w} className={`cal-dow${i === 0 ? ' sun' : i === 6 ? ' sat' : ''}`}>{w}</div>)}
            {grid.map((c) => {
              const n = counts[c.date] ?? 0;
              return (
                <button key={c.date} type="button" role="gridcell" aria-selected={c.date === date}
                  className={`cal-cell${c.inMonth ? '' : ' out'}${c.date === date ? ' sel' : ''}${c.date === today ? ' today' : ''}`}
                  onClick={() => pick(c.date)} title={n ? `${c.date} · 일지 ${n}건` : c.date}>
                  <span>{Number(c.date.slice(8))}</span>
                  {n > 0 && <b className="cal-count">{n}</b>}
                </button>
              );
            })}
          </div>
          <p className="hint">숫자는 현재 필터 기준 그 날의 일지 수입니다.</p>
        </aside>

        <div className="log-list">
          <div className="row between">
            <h3>{date} <small className="hint">({WEEK[new Date(`${date}T00:00:00`).getDay()]}) · 일지 {items.length}건</small></h3>
            <button type="button" onClick={() => setCreating(true)}>이 날짜에 작성</button>
          </div>
          {list.error && <p className="field-error">{list.error}</p>}
          {items.map((l) => {
            const mine = !!actor && l.authorId === actor.id;
            return (
              <article key={l.id} className={`card log-card${mine ? ' mine' : ''}`}>
                <header>
                  <strong>{l.projectName}</strong>
                  <span className="badge">{STATUS_LABEL[l.projectStatus]}</span>
                  <span className="hint">{l.teamName}</span>
                  <span className="grow" />
                  <span>{l.authorName}{l.authorTeam ? ` · ${l.authorTeam}` : ''}{mine && <span className="badge">내 일지</span>}</span>
                </header>
                <ul className="task-previews">
                  {l.tasks.map((t, i) => <li key={t.id}><span className="badge">{t.milestone}</span> {t.title && <strong>{t.title}</strong>}{t.title && t.contentPreview ? ' — ' : ''}{t.contentPreview || (!t.title ? '(내용 없음)' : '')}{t.attachmentCount > 0 && <small className="hint"> · 첨부 {t.attachmentCount}</small>}<span className="sr-only"> TASK {i + 1}</span></li>)}
                </ul>
                <footer>
                  <small className="hint">
                    {l.todoCount > 0 && `To-Do ${l.todoCount} · `}{l.issueCount > 0 && `Issue ${l.issueCount} · `}{l.achievementCount > 0 && `성과 ${l.achievementCount} · `}
                    revision {l.revision} · {timeOf(l.updatedAt)} 수정
                  </small>
                  <span className="grow" />
                  <button type="button" onClick={() => setViewId(l.id)}>보기</button>
                  {mine && <a className="btn primary-link" href={`#/logs/${l.projectId}/${l.workDate}`}>이어서 작성</a>}
                </footer>
              </article>
            );
          })}
          {list.data && items.length === 0 && (
            <div className="notice">이 날짜에는 (현재 필터에 맞는) 업무일지가 없습니다. 필터를 풀거나 <button type="button" className="link" onClick={() => setCreating(true)}>업무일지를 작성</button>해 보세요.</div>
          )}
        </div>
      </div>

      {creating && <NewLog projects={all} date={date} onClose={() => setCreating(false)} />}
      {viewId && <LogView logId={viewId} onClose={() => setViewId(null)} />}
    </section>
  );
}

/** 작성 시작: 프로젝트(드롭박스 + 필터)와 날짜를 고른 뒤 작성 화면으로 이동 */
function NewLog({ projects, date, onClose }: { projects: Project[]; date: string; onClose: () => void }) {
  const toast = useToast();
  const { actor } = useSession();
  const [filters, setFilters] = usePickerFilters();
  const [pid, setPid] = useState('');
  const [d, setD] = useState(date);
  const [existing, setExisting] = useState<boolean | null>(null);
  useEffect(() => {
    setExisting(null);
    if (!pid || !actor || !d) return;
    let alive = true;
    api.get<List<{ id: string; deletedAt: string | null }>>(`/projects/${pid}/logs${qs({ date: d, authorId: actor.id })}`)
      .then((r) => { if (alive) setExisting(r.items.length > 0); }).catch((e) => { if (alive) toast('err', errText(e)); });
    return () => { alive = false; };
  }, [pid, d, actor]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Modal title="업무일지 작성" wide onClose={onClose}>
      {!actor && <p className="notice">상단에서 <strong>작성자</strong>를 먼저 선택해 주세요.</p>}
      <ProjectPicker projects={projects} value={pid} onChange={setPid} filters={filters} onFiltersChange={setFilters} />
      <div className="row">
        <Field label="업무 날짜"><input type="date" value={d} onChange={(e) => e.target.value && setD(e.target.value)} /></Field>
        {pid && existing === true && <span className="hint">이 날짜에 이미 쓴 일지가 있어 <strong>이어서 작성</strong>합니다.</span>}
        {pid && existing === false && <span className="hint">새 일지를 만듭니다.</span>}
      </div>
      <p className="hint">프로젝트가 없으면 <a href="#/projects">프로젝트 탭</a>에서 먼저 만드세요. 한 프로젝트·작성자·날짜에는 일지가 하나입니다.</p>
      <div className="row end">
        <button type="button" onClick={onClose}>취소</button>
        <button type="button" className="primary" disabled={!pid || !actor} onClick={() => { onClose(); window.location.hash = `#/logs/${pid}/${d}`; }}>
          {existing ? '이어서 작성' : '작성 시작'}
        </button>
      </div>
    </Modal>
  );
}
