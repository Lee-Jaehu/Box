/** 왼쪽 내비게이션 트리(담당 → 팀 → PJT → Worklog·자료 생성기)용 순수 함수 (결정 I37). */
import type { Project } from '../api/types';

export interface MilestoneSummary { total: number; completed: number; cancelled: number }
export type NavProject = Pick<Project, 'id' | 'name' | 'teamId' | 'teamName' | 'divisionId' | 'divisionName' | 'status' | 'ownerUserId' | 'memberIds'>
  & { milestoneSummary?: MilestoneSummary };

export interface TeamNode { key: string; id: string | null; name: string; projects: NavProject[] }
export interface DivisionNode { key: string; id: string | null; name: string; teams: TeamNode[] }

export const NO_DIVISION = '담당 미지정';
export const NO_TEAM = '팀 미지정';

const byName = (a: { name: string }, b: { name: string }) => a.name.localeCompare(b.name, 'ko');

/** 마일스톤 기준 완료: 일반·수시 업무를 뺀 마일스톤이 모두 완료·취소이고 1개 이상 완료, 또는 프로젝트 상태가 '완료'. */
export function isProjectDone(p: NavProject): boolean {
  if (p.status === 'completed') return true;
  const s = p.milestoneSummary;
  return !!s && s.total > 0 && s.completed > 0 && s.completed + s.cancelled === s.total;
}

export function milestoneLabel(p: NavProject): string {
  const s = p.milestoneSummary;
  if (!s || s.total === 0) return '마일스톤 없음 (일반·수시 업무만)';
  return `마일스톤 ${s.completed}/${s.total} 완료${s.cancelled ? ` · 취소 ${s.cancelled}` : ''}`;
}

/** 담당 → 팀 → PJT. 이름순(미지정은 맨 뒤), 팀 안에서는 진행 중 과제가 먼저, 완료 과제는 뒤. */
export function buildTree(projects: NavProject[]): DivisionNode[] {
  const divisions = new Map<string, DivisionNode>();
  for (const p of projects) {
    const dKey = `d:${p.divisionId ?? '-'}`;
    let d = divisions.get(dKey);
    if (!d) { d = { key: dKey, id: p.divisionId, name: p.divisionName ?? NO_DIVISION, teams: [] }; divisions.set(dKey, d); }
    const tKey = `t:${p.teamId ?? '-'}`;
    let t = d.teams.find((x) => x.key === tKey);
    if (!t) { t = { key: tKey, id: p.teamId ?? null, name: p.teamName ?? NO_TEAM, projects: [] }; d.teams.push(t); }
    t.projects.push(p);
  }
  const lastIfMissing = (a: { id: string | null; name: string }, b: { id: string | null; name: string }) =>
    (a.id === null ? 1 : 0) - (b.id === null ? 1 : 0) || byName(a, b);
  const out = [...divisions.values()].sort(lastIfMissing);
  for (const d of out) {
    d.teams.sort(lastIfMissing);
    for (const t of d.teams) t.projects.sort((a, b) => Number(isProjectDone(a)) - Number(isProjectDone(b)) || byName(a, b));
  }
  return out;
}

/** 검색어(과제명·팀·담당)와 '내 프로젝트만'으로 거른 트리. 거른 결과에서 빈 팀·담당은 뺀다. */
export function filterTree(tree: DivisionNode[], q: string, mineOf: string | null): DivisionNode[] {
  const needle = q.trim().toLowerCase();
  const keep = (d: DivisionNode, t: TeamNode, p: NavProject) =>
    (!mineOf || p.ownerUserId === mineOf || p.memberIds.includes(mineOf))
    && (!needle || [p.name, t.name, d.name].some((s) => s.toLowerCase().includes(needle)));
  return tree.map((d) => ({ ...d, teams: d.teams.map((t) => ({ ...t, projects: t.projects.filter((p) => keep(d, t, p)) })).filter((t) => t.projects.length) }))
    .filter((d) => d.teams.length);
}

// ── 노드 키와 주소 ──────────────────────────────────────────────────────────
export const key = {
  project: (pid: string) => `p:${pid}`,
  worklog: (pid: string) => `w:${pid}`,
  todos: (pid: string) => `wt:${pid}`,
  issues: (pid: string) => `wi:${pid}`,
  reports: (pid: string) => `r:${pid}`,
  reportWeekly: (pid: string) => `rw:${pid}`,
  reportExec: (pid: string) => `re:${pid}`,
};

export const href = {
  project: (pid: string) => `#/projects/${pid}`,
  worklog: (pid: string) => `#/logs?project=${pid}`,
  todos: (pid: string) => `#/todos/${pid}`,
  issues: (pid: string) => `#/issues/${pid}`,
  reports: (pid: string) => `#/reports?project=${pid}`,
  reportWeekly: (pid: string) => `#/reports?project=${pid}&template=weekly`,
  reportExec: (pid: string) => `#/reports?project=${pid}&template=exec`,
};

/** 아래쪽 '전체 보기·관리' 묶음 */
export const GLOBAL_LINKS: { key: string; label: string; href: string }[] = [
  { key: 'all:logs', label: '전체 업무일지', href: '#/logs' },
  { key: 'all:todos', label: '전체 To-Do', href: '#/todos' },
  { key: 'all:issues', label: '전체 Issue', href: '#/issues' },
  { key: 'all:reports', label: '보고자료 (여러 과제·팀장 요약)', href: '#/reports' },
  { key: 'all:projects', label: '프로젝트 목록', href: '#/projects' },
  { key: 'all:masters', label: '조직·사용자', href: '#/masters' },
  { key: 'all:ops', label: '운영', href: '#/ops' },
];

function splitHash(hash: string): { parts: string[]; query: URLSearchParams } {
  const [path, qs = ''] = hash.replace(/^#\/?/, '').split('?');
  return { parts: path.split('/').filter(Boolean), query: new URLSearchParams(qs) };
}

/** 지금 주소의 과제 (트리 경로 펼침·오른쪽 과제 탭 줄용). 없으면 null. */
export function projectOfHash(hash: string): string | null {
  const { parts, query } = splitHash(hash);
  if ((parts[0] === 'projects' || parts[0] === 'todos' || parts[0] === 'issues' || parts[0] === 'logs') && parts[1]) return parts[1];
  if (parts[0] === 'logs' || parts[0] === 'reports') return query.get('project');
  return null;
}

/** 주소 → 선택할 노드와 펼쳐야 할 노드(담당·팀·PJT·Worklog/자료 생성기). */
export function activeKeys(hash: string, projects: NavProject[]): { selected: string | null; open: string[] } {
  const { parts, query } = splitHash(hash);
  const pid = projectOfHash(hash);
  const p = pid ? projects.find((x) => x.id === pid) : undefined;
  const base = p ? [`d:${p.divisionId ?? '-'}`, `t:${p.teamId ?? '-'}`, key.project(p.id)] : [];
  const top = parts[0] || 'logs';
  if (!pid) {
    const global = GLOBAL_LINKS.find((g) => g.key === `all:${top}`);
    return { selected: global?.key ?? null, open: [] };
  }
  switch (top) {
    case 'projects': return { selected: key.project(pid), open: base };
    case 'logs': return { selected: key.worklog(pid), open: [...base, key.worklog(pid)] };
    case 'todos': return { selected: key.todos(pid), open: [...base, key.worklog(pid)] };
    case 'issues': return { selected: key.issues(pid), open: [...base, key.worklog(pid)] };
    case 'reports': {
      const t = query.get('template');
      const selected = t === 'weekly' ? key.reportWeekly(pid) : t === 'exec' ? key.reportExec(pid) : key.reports(pid);
      return { selected, open: [...base, key.reports(pid)] };
    }
    default: return { selected: null, open: base };
  }
}
