import { useEffect } from 'react';
import { api } from '../api/client';
import type { List, Project } from '../api/types';
import { STATUS_LABEL, useAsync } from '../ui';
import { LogPage } from './LogPage';
import { ProjectPicker, usePickerFilters } from './ProjectPicker';
import { TrackerPage } from './TrackerPage';

const LAST_KEY = 'worklog.lastProject';

/** 업무일지 작성 화면: 조회 화면에서 프로젝트·날짜를 고른 뒤에만 들어온다. */
export function LogEditorPage({ projectId, date }: { projectId: string; date?: string }) {
  const detail = useAsync(() => api.get<Project>(`/projects/${projectId}`), [projectId]);
  return (
    <section>
      <p className="crumb"><a href={`#/logs${date ? `?date=${date}` : ''}`}>← 업무일지 목록</a></p>
      <div className="row between">
        <h2>업무일지 작성{detail.data ? ` · ${detail.data.name}` : ''}</h2>
        {detail.data && <span className="hint">{detail.data.divisionName ? `${detail.data.divisionName} / ` : ''}{detail.data.teamName} · 대표 {detail.data.ownerName} · {STATUS_LABEL[detail.data.status]} · <a href={`#/projects/${projectId}`}>프로젝트 기준정보</a></span>}
      </div>
      {detail.error && <p className="field-error">{detail.error} <a href="#/logs">목록으로</a></p>}
      {detail.data && (
        <>
          {detail.data.status !== 'in_progress' && detail.data.status !== 'preparing' && (
            <p className="notice">이 프로젝트는 ‘{STATUS_LABEL[detail.data.status]}’ 상태입니다. 기록은 계속 남길 수 있습니다.</p>
          )}
          <LogPage key={projectId} project={detail.data} reloadProject={detail.reload} initialDate={date} />
        </>
      )}
    </section>
  );
}

/** To-Do / Issue 탭: 날짜별 기록이 아니라 프로젝트 단위 관리라서, 프로젝트 드롭박스(+필터)로 대상을 고른다. */
export function TrackerWorkspace({ kind, projectId }: { kind: 'todos' | 'issues'; projectId?: string }) {
  const list = useAsync(() => api.get<List<Project>>('/projects?limit=200'), []);
  const projects = list.data?.items ?? [];
  const detail = useAsync(() => (projectId ? api.get<Project>(`/projects/${projectId}`) : Promise.resolve(null)), [projectId]);
  const [filters, setFilters] = usePickerFilters();

  useEffect(() => {
    if (projectId) { try { localStorage.setItem(LAST_KEY, projectId); } catch { /* 무시 */ } }
  }, [projectId]);

  let last: string | null = null;
  try { last = localStorage.getItem(LAST_KEY); } catch { /* 무시 */ }
  const lastProject = projects.find((p) => p.id === last);

  return (
    <section>
      <h2>{kind === 'todos' ? 'To-Do' : 'Issue'}</h2>
      <ProjectPicker projects={projects} value={projectId ?? ''} filters={filters} onFiltersChange={setFilters}
        onChange={(id) => { window.location.hash = id ? `#/${kind}/${id}` : `#/${kind}`; }} />
      {projectId && <p><a href={`#/projects/${projectId}`}>프로젝트 기준정보</a></p>}
      {!projectId && (
        <div className="notice">
          {projects.length === 0
            ? <>등록된 프로젝트가 없습니다. 먼저 <a href="#/projects">프로젝트 탭</a>에서 프로젝트를 만드세요.</>
            : '관리할 프로젝트를 선택하세요. 기본은 내가 대표이거나 참여하는 프로젝트이며, 옆의 필터로 범위를 바꿀 수 있습니다.'}
          {lastProject && <> 최근 사용: <a href={`#/${kind}/${lastProject.id}`}>{lastProject.name}</a></>}
        </div>
      )}
      {projectId && detail.error && <p className="field-error">{detail.error}</p>}
      {projectId && detail.data && (
        <>
          {detail.data.status !== 'in_progress' && detail.data.status !== 'preparing' && (
            <p className="notice">이 프로젝트는 ‘{STATUS_LABEL[detail.data.status]}’ 상태입니다.</p>
          )}
          <TrackerPage key={projectId} kind={kind === 'todos' ? 'todo' : 'issue'} project={detail.data} />
        </>
      )}
    </section>
  );
}
