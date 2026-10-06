// 프로젝트 선택기 필터(순수 로직). 업무일지·To-Do·Issue 탭이 같은 규칙을 쓴다.
import type { Project } from '../api/types';

export interface PickerFilters {
  scope: 'mine' | 'all'; // mine = 내가 대표이거나 참여자인 프로젝트
  divisionId: string;
  teamId: string;
  status: string; // '' = 전체
  q: string;
}

export const defaultFilters = (hasActor: boolean): PickerFilters => ({ scope: hasActor ? 'mine' : 'all', divisionId: '', teamId: '', status: '', q: '' });

export function isMine(p: Project, actorId: string | null): boolean {
  return !!actorId && (p.ownerUserId === actorId || p.memberIds.includes(actorId));
}

export function filterProjects(projects: Project[], f: PickerFilters, actorId: string | null): Project[] {
  const q = f.q.trim().toLowerCase();
  return projects.filter((p) =>
    (f.scope === 'all' || !actorId || isMine(p, actorId)) &&
    (!f.divisionId || p.divisionId === f.divisionId) &&
    (!f.teamId || p.teamId === f.teamId) &&
    (!f.status || p.status === f.status) &&
    (!q || p.name.toLowerCase().includes(q)),
  );
}

export function uniqueOptions(projects: Project[], key: 'division' | 'team'): { id: string; name: string }[] {
  const m = new Map<string, string>();
  for (const p of projects) {
    const id = key === 'division' ? p.divisionId : p.teamId;
    const name = key === 'division' ? p.divisionName : p.teamName;
    if (id && name) m.set(id, name);
  }
  return [...m].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name, 'ko'));
}

const KEY = 'worklog.pickerFilters';

export function loadFilters(hasActor: boolean): PickerFilters {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...defaultFilters(hasActor), ...(JSON.parse(raw) as Partial<PickerFilters>) };
  } catch { /* 저장소를 못 써도 기본값으로 동작 */ }
  return defaultFilters(hasActor);
}

export function saveFilters(f: PickerFilters): void {
  try { localStorage.setItem(KEY, JSON.stringify(f)); } catch { /* 무시 */ }
}
