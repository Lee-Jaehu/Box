import { describe, expect, it } from 'vitest';
import type { User } from '../api/types';
import { candidateUsers, ownerAfterTeamChange } from './teamUsers';

const U = (id: string, teamId: string): User => ({ id, name: id, teamId, employeeNumber: null, externalKey: null, active: true, revision: 1 });
const users = [U('a', 't1'), U('b', 't1'), U('c', 't2')];

describe('team based owner candidates', () => {
  it('shows only the selected team members by default', () => {
    expect(candidateUsers(users, 't1', false).map((u) => u.id)).toEqual(['a', 'b']);
    expect(candidateUsers(users, 't2', false).map((u) => u.id)).toEqual(['c']);
  });
  it('shows nobody until a team is chosen, unless other teams are allowed', () => {
    expect(candidateUsers(users, '', false)).toEqual([]);
    expect(candidateUsers(users, '', true)).toHaveLength(3);
  });
  it('other-team toggle shows everyone; already selected people stay visible', () => {
    expect(candidateUsers(users, 't1', true)).toHaveLength(3);
    expect(candidateUsers(users, 't1', false, ['c']).map((u) => u.id)).toEqual(['a', 'b', 'c']);
  });
  it('changing team clears an owner who is not in the new team', () => {
    expect(ownerAfterTeamChange(users, 'a', 't1', false)).toBe('a');
    expect(ownerAfterTeamChange(users, 'a', 't2', false)).toBe('');
    expect(ownerAfterTeamChange(users, 'a', 't2', true)).toBe('a');
    expect(ownerAfterTeamChange(users, '', 't2', false)).toBe('');
  });
});
