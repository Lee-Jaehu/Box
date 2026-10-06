// 프로젝트의 대표 담당자/참여자 후보: 선택한 담당 팀의 구성원이 기본이고, 필요하면 다른 팀 사람도 보이게 한다.
import type { User } from '../api/types';

export function candidateUsers(users: User[], teamId: string, includeOtherTeams: boolean, keepIds: string[] = []): User[] {
  if (!teamId && !includeOtherTeams) return [];
  return users.filter((u) => includeOtherTeams || u.teamId === teamId || keepIds.includes(u.id));
}

/** 팀을 바꿨을 때 대표 담당자: 새 팀 소속이면 유지, 아니면 비운다(다른 팀 사람도 허용 중이면 유지). */
export function ownerAfterTeamChange(users: User[], ownerId: string, newTeamId: string, includeOtherTeams: boolean): string {
  if (!ownerId || includeOtherTeams) return ownerId;
  return users.find((u) => u.id === ownerId)?.teamId === newTeamId ? ownerId : '';
}
