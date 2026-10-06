import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { NavProject } from './navTree';
import { SideNav } from './SideNav';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const P = (id: string, name: string, over: Partial<NavProject> = {}): NavProject => ({
  id, name, teamId: 'T1', teamName: '자동보정팀', divisionId: 'D1', divisionName: '제조DX담당', status: 'in_progress',
  ownerUserId: 'U1', memberIds: ['U1'], milestoneSummary: { total: 1, completed: 0, cancelled: 0 }, ...over,
});
const projects = [
  P('p1', '재료교체 불량 개선'),
  P('p2', '코팅 온도 관리', { milestoneSummary: { total: 2, completed: 2, cancelled: 0 } }),
  P('p3', '추적 데이터 통합', { teamId: 'T2', teamName: '추적솔루션팀' }),
];

let host: HTMLDivElement;
let root: ReturnType<typeof createRoot>;
const row = (k: string) => host.querySelector<HTMLElement>(`[data-key="${k}"]`);
const render = async (hash: string) => { await act(async () => { root.render(<SideNav hash={hash} projects={projects} />); }); };

beforeEach(() => {
  localStorage.clear();
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
});

describe('SideNav', () => {
  it('처음에는 담당만 보이고, 담당 → 팀 → PJT 순으로 펼친다', async () => {
    await render('#/logs');
    expect(row('d:D1')?.textContent).toContain('제조DX담당');
    expect(row('t:T1')).toBeNull();
    await act(async () => row('d:D1')!.click());
    await act(async () => row('t:T1')!.click());
    expect(row('p:p1')?.getAttribute('href')).toBe('#/projects/p1');
    expect(row('all:logs')?.className).toContain('active');
  });

  it('마일스톤이 모두 완료된 PJT는 done(검회색)으로 표시하고 완료 표시를 붙인다', async () => {
    await render('#/projects/p2');
    expect(row('p:p2')?.className).toContain('done');
    expect(row('p:p2')?.textContent).toContain('완료');
    expect(row('p:p1')?.className).not.toContain('done');
    expect(row('p:p2')?.className).toContain('active');
  });

  it('주소의 과제 경로를 자동으로 펴고, Worklog 아래 To-Do·Issue, 자료 생성기 아래 두 자료로 이어진다', async () => {
    await render('#/todos/p1');
    expect(row('wt:p1')?.className).toContain('active');
    expect(row('w:p1')?.getAttribute('href')).toBe('#/logs?project=p1');
    expect(row('wi:p1')?.getAttribute('href')).toBe('#/issues/p1');
    await act(async () => row('r:p1')!.querySelector<HTMLButtonElement>('.tree-caret')!.click());
    expect(row('rw:p1')?.getAttribute('href')).toBe('#/reports?project=p1&template=weekly');
    expect(row('re:p1')?.getAttribute('href')).toBe('#/reports?project=p1&template=exec');
  });

  it('검색하면 맞는 과제와 그 상위만 펼쳐 보여 준다', async () => {
    await render('#/logs');
    const input = host.querySelector<HTMLInputElement>('input[type=search]')!;
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
      setter.call(input, '추적');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(row('p:p3')).not.toBeNull();
    expect(row('p:p1')).toBeNull();
    expect(row('t:T1')).toBeNull();
  });
});
