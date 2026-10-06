/** 과제 Worklog 화면 (왼쪽 트리 PJT ▸ 전체 Worklog / User ▸ Worklog): 위 = 경로·사람 선택, 가운데 = 달력+일지 목록,
 *  아래 = To-Do·Issue 패널 (별도 탭이 아니라 Worklog 안에서 관리). User의 Worklog면 일지·To-Do·Issue 모두 그 사람 기준. 결정 I37. */
import { api } from '../api/client';
import type { Project } from '../api/types';
import { STATUS_LABEL, useAsync } from '../ui';
import { LogsHome } from './LogsHome';
import { href, isProjectDone, milestoneLabel, peopleOf, ROLE_LABEL, type NavProject } from './navTree';
import { TrackerPage } from './TrackerPage';

export function ProjectWorklog({ projectId, authorId, initialDate }: { projectId: string; authorId?: string; initialDate?: string }) {
  const p = useAsync(() => api.get<Project & NavProject>(`/projects/${projectId}`), [projectId]);
  const project = p.data;
  const people = project ? peopleOf(project) : [];
  const person = people.find((x) => x.id === authorId);
  return (
    <div className="project-worklog">
      <div className="workbar">
        <div className="row between tight">
          <p className="crumb">
            {project
              ? <>{project.divisionName ?? '담당 미지정'} › {project.teamName ?? '팀 미지정'} › <a href={href.project(projectId)}><strong className={isProjectDone(project) ? 'done-text' : ''}>{project.name}</strong></a>
                {' › '}<strong>{authorId ? (person?.name ?? '선택한 사람') : '전체'}</strong></>
              : p.error ?? '불러오는 중…'}
            {project && <span className="badge" title={milestoneLabel(project)}>{isProjectDone(project) ? '완료' : STATUS_LABEL[project.status] ?? project.status}</span>}
          </p>
          <span className="row tight">
            {project && (
              <label className="check hint">사람
                <select value={authorId ?? ''} aria-label="사람 선택"
                  onChange={(e) => { window.location.hash = e.target.value ? href.personWorklog(projectId, e.target.value) : href.worklog(projectId); }}>
                  <option value="">전체</option>
                  {people.map((x) => <option key={x.id} value={x.id}>{x.name ?? x.id} ({ROLE_LABEL[x.role]})</option>)}
                </select>
              </label>
            )}
            <a className="hint" href={href.reports(projectId)}>이 과제로 자료 만들기 →</a>
          </span>
        </div>
      </div>
      <LogsHome key={`${projectId}|${authorId ?? ''}|${initialDate ?? ''}`} initialDate={initialDate} projectId={projectId} authorId={authorId} />
      {project && (
        <div className="tracker-panels">
          <section className="card" aria-label="To-Do">
            <h3>To-Do {person && <small className="hint">· {person.name} 담당</small>}</h3>
            <TrackerPage key={`todo|${authorId ?? ''}`} kind="todo" project={project} initialAssignee={authorId} compact />
          </section>
          <section className="card" aria-label="Issue">
            <h3>Issue {person && <small className="hint">· {person.name} 담당</small>}</h3>
            <TrackerPage key={`issue|${authorId ?? ''}`} kind="issue" project={project} initialAssignee={authorId} compact />
          </section>
        </div>
      )}
    </div>
  );
}
