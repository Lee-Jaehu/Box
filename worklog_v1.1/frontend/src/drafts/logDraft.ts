// 일지 초안 모델과 순수 로직(서버/React 없이 단위 테스트 가능).
//  - 초안은 브라우저 IndexedDB 에 저장되며 '서버 저장'과 구별된다.
//  - 서버 저장이 진행되는 동안 새 입력이 생기면 이전 저장 응답으로 최신 초안을 지우지 않는다(version 비교).
import { emptyDocument, hasContent, collectImageUseIds, type WorklogDocument } from '../editor/document';
import type { ServerLog } from '../api/types';
import { createId } from "../utils/id";

export interface DraftAttachment {
  id: string; // task_attachments.id = 본문 image node 의 attachmentUseId (클라이언트 UUID, 서버가 그대로 보존)
  attachmentId: string;
  title: string;
  description: string;
  fileName: string;
  mediaType: string;
  isImage: boolean;
}
export interface DraftTask {
  id: string;
  title: string; // TASK 이름(선택, 빈 문자열 = 없음)
  milestoneId: string;
  content: WorklogDocument;
  performedStart: string | null;
  performedEnd: string | null;
  attachments: DraftAttachment[];
}
export interface DraftTracker {
  clientEntryId: string;
  content: WorklogDocument;
  assigneeId: string | null;
  dueDate: string | null;
  impact?: WorklogDocument | null;
  response?: WorklogDocument | null;
}
export interface DraftAchievement {
  id: string;
  type: 'quantitative' | 'qualitative';
  presetKey: string;
  title: string;
  content: WorklogDocument | null;
  numeric: Record<string, string>;
  kpiId: string | null;
  measuredOn: string | null;
  periodStart: string | null;
  periodEnd: string | null;
}
export interface LogDraft {
  version: number; // 로컬 변경 카운터
  baseRevision: number; // 이 초안이 기준으로 삼은 서버 revision (신규 0)
  tasks: DraftTask[];
  newTodos: DraftTracker[];
  newIssues: DraftTracker[];
  hiddenRefIds: string[];
  achievements: DraftAchievement[];
  lesson: WorklogDocument | null;
  note: WorklogDocument | null;
  collaboratorIds: string[];
  savedAt: string; // 마지막 로컬 저장 시각
}

export const uid = (): string => createId();

export function newTask(milestoneId: string, today: string): DraftTask {
  return { id: uid(), title: '', milestoneId, content: emptyDocument(), performedStart: today, performedEnd: today, attachments: [] };
}

export function emptyDraft(milestoneId: string, today: string): LogDraft {
  return {
    version: 0, baseRevision: 0, tasks: [newTask(milestoneId, today)], newTodos: [], newIssues: [], hiddenRefIds: [],
    achievements: [], lesson: null, note: null, collaboratorIds: [], savedAt: new Date().toISOString(),
  };
}

export function draftFromServer(log: ServerLog): LogDraft {
  return {
    version: 0,
    baseRevision: log.revision,
    tasks: log.tasks.map((t) => ({
      id: t.id,
      title: t.title ?? '',
      milestoneId: t.milestoneId ?? '',
      content: t.content,
      performedStart: t.performedStart,
      performedEnd: t.performedEnd,
      attachments: t.attachments.map((a) => ({
        id: a.id, attachmentId: a.attachmentId, title: a.title ?? '', description: a.description,
        fileName: a.file.originalName, mediaType: a.file.mediaType, isImage: a.file.isImage,
      })),
    })),
    newTodos: [],
    newIssues: [],
    hiddenRefIds: [],
    achievements: log.achievements.map((a) => ({
      id: a.id, type: a.type, presetKey: a.presetKey, title: a.title ?? '', content: a.content,
      numeric: Object.fromEntries(Object.entries(a.numericPayload ?? {}).filter(([, v]) => typeof v === 'string' || typeof v === 'number').map(([k, v]) => [k, String(v)])),
      kpiId: a.kpiId, measuredOn: a.measuredOn, periodStart: a.periodStart, periodEnd: a.periodEnd,
    })),
    lesson: log.lessonLearned,
    note: log.note,
    collaboratorIds: log.collaborators.map((c) => c.userId),
    savedAt: new Date().toISOString(),
  };
}

const NUMERIC_KEYS = ['metricName', 'beforeValue', 'afterValue', 'targetValue', 'value', 'unit', 'currency', 'comparisonBasis', 'measurementScope', 'frequency', 'summaryText'];

export function toSaveBody(d: LogDraft): Record<string, unknown> {
  return {
    expectedRevision: d.baseRevision,
    tasks: d.tasks.map((t) => ({
      id: t.id,
      title: t.title.trim() || null,
      milestoneId: t.milestoneId,
      content: t.content,
      performedStart: t.performedStart,
      performedEnd: t.performedEnd,
      attachments: t.attachments.map((a) => ({ id: a.id, attachmentId: a.attachmentId, title: a.title || null, description: a.description })),
    })),
    newTodos: d.newTodos.map((n) => ({ clientEntryId: n.clientEntryId, content: n.content, assigneeId: n.assigneeId, dueDate: n.dueDate })),
    newIssues: d.newIssues.map((n) => ({
      clientEntryId: n.clientEntryId, content: n.content, assigneeId: n.assigneeId, dueDate: n.dueDate, impact: n.impact ?? null, response: n.response ?? null,
    })),
    hiddenTrackerRefIds: d.hiddenRefIds,
    achievements: d.achievements.map((a) => ({
      id: a.id, type: a.type, presetKey: a.presetKey, title: a.title || null, content: a.content && hasContent(a.content.doc) ? a.content : null,
      numericPayload: a.type === 'quantitative' ? Object.fromEntries(NUMERIC_KEYS.filter((k) => a.numeric[k]).map((k) => [k, a.numeric[k]])) : null,
      kpiId: a.kpiId, measuredOn: a.measuredOn, periodStart: a.periodStart, periodEnd: a.periodEnd,
    })),
    lessonLearned: d.lesson && hasContent(d.lesson.doc) ? d.lesson : null,
    note: d.note && hasContent(d.note.doc) ? d.note : null,
    collaboratorIds: d.collaboratorIds,
  };
}

export interface ClientIssue { path: string; message: string }

/** 서버 저장 전에 잡을 수 있는 입력 문제. 최종 판단은 서버(필드 오류)가 한다. */
export function validateDraft(d: LogDraft): ClientIssue[] {
  const out: ClientIssue[] = [];
  d.tasks.forEach((t, i) => {
    if (!hasContent(t.content.doc)) out.push({ path: `tasks[${i}].content`, message: `TASK ${i + 1}: 내용을 입력해 주세요.` });
    if (!t.milestoneId) out.push({ path: `tasks[${i}].milestoneId`, message: `TASK ${i + 1}: 마일스톤을 선택해 주세요.` });
    if (t.performedStart && t.performedEnd && t.performedEnd < t.performedStart) {
      out.push({ path: `tasks[${i}].performedEnd`, message: `TASK ${i + 1}: 종료일은 시작일보다 빠를 수 없습니다.` });
    }
    for (const a of t.attachments) if (a.isImage && !a.description.trim()) out.push({ path: `tasks[${i}].attachments`, message: `TASK ${i + 1}: '${a.fileName}' 이미지 상세 설명을 입력해 주세요.` });
    for (const id of collectImageUseIds(t.content.doc)) {
      if (!t.attachments.some((a) => a.id === id)) out.push({ path: `tasks[${i}].content`, message: `TASK ${i + 1}: 첨부를 찾을 수 없는 이미지가 있습니다. 다시 첨부해 주세요.` });
    }
  });
  d.newTodos.forEach((n, i) => { if (!hasContent(n.content.doc)) out.push({ path: `newTodos[${i}].content`, message: `To-Do ${i + 1}: 내용을 입력해 주세요.` }); });
  d.newIssues.forEach((n, i) => { if (!hasContent(n.content.doc)) out.push({ path: `newIssues[${i}].content`, message: `Issue ${i + 1}: 내용을 입력해 주세요.` }); });
  return out;
}

/** 입력이 하나라도 있는 초안인가(빈 초안은 저장/보관하지 않는다) */
export function isMeaningful(d: LogDraft): boolean {
  return d.tasks.some((t) => hasContent(t.content.doc) || t.attachments.length > 0) || d.newTodos.length > 0 || d.newIssues.length > 0 ||
    d.achievements.length > 0 || !!(d.lesson && hasContent(d.lesson.doc)) || !!(d.note && hasContent(d.note.doc)) || d.collaboratorIds.length > 0;
}

/**
 * 서버 저장 성공 후 초안 재구성.
 *  - 저장하는 동안 사용자가 더 입력했다면(current.version !== sentVersion) 현재 초안을 유지하고 baseRevision 만 새 revision 으로 올린다.
 *  - 그렇지 않으면 서버 응답으로 초안을 다시 만든다(서버가 원본).
 *  - 서버에 등록된 신규 To-Do/Issue 는 초안에서 제거한다(재저장 시 중복 등록 방지; 서버에서도 clientEntryId 로 막힌다).
 */
export function reconcileAfterSave(current: LogDraft, sentVersion: number, sentBody: { newTodos: { clientEntryId: string }[]; newIssues: { clientEntryId: string }[]; hiddenTrackerRefIds: string[] }, serverLog: ServerLog): LogDraft {
  if (current.version === sentVersion) return draftFromServer(serverLog);
  const sentEntries = new Set([...sentBody.newTodos, ...sentBody.newIssues].map((n) => n.clientEntryId));
  return {
    ...current,
    baseRevision: serverLog.revision,
    newTodos: current.newTodos.filter((n) => !sentEntries.has(n.clientEntryId)),
    newIssues: current.newIssues.filter((n) => !sentEntries.has(n.clientEntryId)),
    hiddenRefIds: current.hiddenRefIds.filter((id) => !sentBody.hiddenTrackerRefIds.includes(id)),
  };
}

export function draftKey(parts: { instanceId: string; generation: number; actorId: string; projectId: string; date: string }): string {
  return [parts.instanceId, parts.generation, parts.actorId, parts.projectId, parts.date].join('|');
}

export function parseDraftKey(key: string): { instanceId: string; generation: number; actorId: string; projectId: string; date: string } | null {
  const p = key.split('|');
  if (p.length !== 5 || Number.isNaN(Number(p[1]))) return null;
  return { instanceId: p[0], generation: Number(p[1]), actorId: p[2], projectId: p[3], date: p[4] };
}
