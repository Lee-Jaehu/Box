import { describe, expect, it } from 'vitest';
import { activeKeys, buildTree, filterTree, isProjectDone, NO_DIVISION, NO_TEAM, type NavProject } from './navTree';

const P = (id: string, over: Partial<NavProject> = {}): NavProject => ({
  id, name: `과제${id}`, teamId: 'T1', teamName: '자동보정팀', divisionId: 'D1', divisionName: '제조DX담당', status: 'in_progress',
  ownerUserId: 'U1', memberIds: ['U1'], milestoneSummary: { total: 2, completed: 0, cancelled: 0 }, ...over,
});

describe('isProjectDone (마일스톤 기준 완료 → 검회색)', () => {
  it('일반·수시 업무를 뺀 마일스톤이 모두 완료·취소이고 1개 이상 완료면 완료', () => {
    expect(isProjectDone(P('a', { milestoneSummary: { total: 2, completed: 2, cancelled: 0 } }))).toBe(true);
    expect(isProjectDone(P('b', { milestoneSummary: { total: 3, completed: 2, cancelled: 1 } }))).toBe(true);
    expect(isProjectDone(P('c', { milestoneSummary: { total: 3, completed: 2, cancelled: 0 } }))).toBe(false);
  });
  it('모두 취소이거나 마일스톤이 없으면 완료가 아니고, 프로젝트 상태가 완료면 완료', () => {
    expect(isProjectDone(P('a', { milestoneSummary: { total: 2, completed: 0, cancelled: 2 } }))).toBe(false);
    expect(isProjectDone(P('b', { milestoneSummary: { total: 0, completed: 0, cancelled: 0 } }))).toBe(false);
    expect(isProjectDone(P('c', { status: 'completed', milestoneSummary: undefined }))).toBe(true);
  });
});

describe('buildTree / filterTree', () => {
  const projects = [
    P('1', { name: '나 과제', milestoneSummary: { total: 1, completed: 1, cancelled: 0 } }),
    P('2', { name: '다 과제' }),
    P('3', { name: '가 과제', teamId: 'T2', teamName: '추적솔루션팀' }),
    P('4', { name: '라 과제', divisionId: 'D0', divisionName: '가공DX담당', teamId: 'T3', teamName: '검증팀' }),
    P('5', { name: '마 과제', divisionId: null, divisionName: null, teamId: 'T9', teamName: null }),
  ];

  it('담당 → 팀 → PJT로 묶고 이름순(미지정은 맨 뒤), 팀 안에서는 완료 과제가 뒤', () => {
    const tree = buildTree(projects);
    expect(tree.map((d) => d.name)).toEqual(['가공DX담당', '제조DX담당', NO_DIVISION]);
    expect(tree[1].teams.map((t) => t.name)).toEqual(['자동보정팀', '추적솔루션팀']);
    expect(tree[1].teams[0].projects.map((p) => p.name)).toEqual(['다 과제', '나 과제']);
    expect(tree[2].teams[0].name).toBe(NO_TEAM);
  });

  it('검색어는 과제·팀·담당 이름에 맞추고, 내 프로젝트만 거르면 빈 팀·담당은 뺀다', () => {
    const tree = buildTree(projects);
    expect(filterTree(tree, '추적', null).flatMap((d) => d.teams.flatMap((t) => t.projects.map((p) => p.id)))).toEqual(['3']);
    expect(filterTree(tree, '라', null).map((d) => d.name)).toEqual(['가공DX담당']);
    expect(filterTree(tree, '', 'U9')).toEqual([]);
  });
});

describe('activeKeys (주소 → 펼칠 경로·선택 노드)', () => {
  const projects = [P('p1')];
  const base = ['d:D1', 't:T1', 'p:p1'];
  it.each([
    ['#/projects/p1', 'p:p1', base],
    ['#/logs?project=p1&date=2026-10-01', 'w:p1', [...base, 'w:p1']],
    ['#/logs/p1/2026-10-01', 'w:p1', [...base, 'w:p1']],
    ['#/todos/p1', 'wt:p1', [...base, 'w:p1']],
    ['#/issues/p1', 'wi:p1', [...base, 'w:p1']],
    ['#/reports?project=p1', 'r:p1', [...base, 'r:p1']],
    ['#/reports?project=p1&template=weekly', 'rw:p1', [...base, 'r:p1']],
    ['#/reports?project=p1&template=exec', 're:p1', [...base, 'r:p1']],
  ])('%s', (hash, selected, open) => {
    expect(activeKeys(hash, projects)).toEqual({ selected, open });
  });
  it('과제가 없는 주소는 아래쪽 전체 보기·관리 항목을 고른다', () => {
    expect(activeKeys('#/logs', projects)).toEqual({ selected: 'all:logs', open: [] });
    expect(activeKeys('#/reports', projects)).toEqual({ selected: 'all:reports', open: [] });
    expect(activeKeys('#/masters', projects).selected).toBe('all:masters');
    expect(activeKeys('', projects).selected).toBe('all:logs');
  });
});
