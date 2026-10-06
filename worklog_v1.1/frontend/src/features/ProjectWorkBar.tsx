/** 과제 단위 Worklog 화면 위의 작은 탭 줄: 과제명 · [업무일지 | To-Do | Issue] (왼쪽 트리의 PJT ▸ Worklog 아래 묶음과 같다) */
import { api } from '../api/client';
import type { Project } from '../api/types';
import { STATUS_LABEL, useAsync } from '../ui';
import { href, isProjectDone, milestoneLabel, type NavProject } from './navTree';

export type WorkTab = 'logs' | 'todos' | 'issues';

export function ProjectWorkBar({ projectId, tab }: { projectId: string; tab: WorkTab }) {
  const p = useAsync(() => api.get<Project & NavProject>(`/projects/${projectId}`), [projectId]);
  const project = p.data;
  const link = (t: WorkTab, label: string, to: string) => <a className={tab === t ? 'active' : ''} href={to}>{label}</a>;
  return (
    <div className="workbar">
      <div className="row between tight">
        <p className="crumb">
          {project ? <>{project.divisionName ?? '담당 미지정'} › {project.teamName ?? '팀 미지정'} › <a href={href.project(projectId)}><strong className={isProjectDone(project) ? 'done-text' : ''}>{project.name}</strong></a></> : '불러오는 중…'}
          {project && <span className="badge" title={milestoneLabel(project)}>{isProjectDone(project) ? '완료' : STATUS_LABEL[project.status] ?? project.status}</span>}
        </p>
        <a className="hint" href={href.reports(projectId)}>이 과제로 자료 만들기 →</a>
      </div>
      <nav className="tabs" aria-label="Worklog">
        {link('logs', '업무일지', href.worklog(projectId))}
        {link('todos', 'To-Do', href.todos(projectId))}
        {link('issues', 'Issue', href.issues(projectId))}
      </nav>
    </div>
  );
}
