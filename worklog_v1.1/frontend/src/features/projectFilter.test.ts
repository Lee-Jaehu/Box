import { describe, expect, it } from 'vitest';
import type { Project } from '../api/types';
import { defaultFilters, filterProjects, uniqueOptions } from './projectFilter';

const P = (id: string, name: string, o: Partial<Project> = {}): Project => ({
  id, name, teamId: 't1', teamName: '업무개선팀', divisionId: 'd1', divisionName: '운영담당', ownerUserId: 'bob', ownerName: '이두리',
  isShortTerm: false, status: 'in_progress', startDate: null, endDate: null, revision: 1, memberIds: ['bob'], ...o,
});
const list = [
  P('1', '검증 절차 개선', { memberIds: ['bob', 'alice'] }),
  P('2', '품질 점검', { teamId: 't2', teamName: '품질팀', divisionId: 'd2', divisionName: '품질담당', ownerUserId: 'carol', memberIds: ['carol'] }),
  P('3', '완료된 일', { status: 'completed', memberIds: ['alice', 'bob'] }),
];

describe('project picker filter', () => {
  it('defaults to "my projects" when an actor is selected, otherwise all', () => {
    expect(defaultFilters(true).scope).toBe('mine');
    expect(defaultFilters(false).scope).toBe('all');
  });
  it('mine = owner or participant', () => {
    const f = defaultFilters(true);
    expect(filterProjects(list, f, 'alice').map((p) => p.id)).toEqual(['1', '3']);
    expect(filterProjects(list, f, 'carol').map((p) => p.id)).toEqual(['2']);
    expect(filterProjects(list, f, 'bob').map((p) => p.id)).toEqual(['1', '3']);   // 대표
  });
  it('scope mine without actor does not hide everything', () => {
    expect(filterProjects(list, defaultFilters(true), null)).toHaveLength(3);
  });
  it('division/team/status/name filters combine', () => {
    const all = { ...defaultFilters(false) };
    expect(filterProjects(list, { ...all, divisionId: 'd2' }, null).map((p) => p.id)).toEqual(['2']);
    expect(filterProjects(list, { ...all, teamId: 't1', status: 'completed' }, null).map((p) => p.id)).toEqual(['3']);
    expect(filterProjects(list, { ...all, q: ' 절차 ' }, null).map((p) => p.id)).toEqual(['1']);
  });
  it('builds division and team options from the projects themselves', () => {
    expect(uniqueOptions(list, 'team').map((o) => o.name)).toEqual(['업무개선팀', '품질팀']);
    expect(uniqueOptions(list, 'division').map((o) => o.id).sort()).toEqual(['d1', 'd2']);
  });
});
