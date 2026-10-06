import type { WorklogDocument } from '../editor/document';

export interface Org { id: string; name: string; kind: 'division' | 'team'; parentId: string | null; externalKey: string | null; active: boolean; revision: number }
export interface User { id: string; name: string; teamId: string; teamName?: string; divisionId?: string | null; divisionName?: string | null; employeeNumber: string | null; externalKey: string | null; active: boolean; revision: number }
export interface Milestone {
  id: string; projectId: string; name: string; isGeneral: boolean; sortOrder: number; status: string;
  plannedStart: string | null; plannedEnd: string | null; baselineStart: string | null; baselineEnd: string | null;
  actualStart: string | null; actualEnd: string | null; baselineConfirmedAt: string | null; revision: number; similarNames?: string[];
}
export interface Kpi { id: string; name: string; unit: string | null; baselineValue: string | null; targetValue: string | null; direction: string | null; active: boolean; revision: number }
export interface Project {
  id: string; name: string; teamId: string; teamName: string | null; divisionId: string | null; divisionName: string | null;
  ownerUserId: string; ownerName: string | null; isShortTerm: boolean; status: string; startDate: string | null; endDate: string | null;
  revision: number; deletedAt?: string | null; memberIds: string[]; backgroundDoc?: WorklogDocument | null; purposeDoc?: WorklogDocument | null; retrospectiveDoc?: WorklogDocument | null;
  milestones?: Milestone[]; kpis?: Kpi[]; hasDetail?: { background: boolean; purpose: boolean; kpis: boolean; milestones: boolean };
}
export interface List<T> { items: T[]; nextCursor: string | null }

export interface AttachmentFile { id: string; originalName: string; mediaType: string; sizeBytes: number; width: number | null; height: number | null; state: string; isImage: boolean }
export interface ServerAttachmentUse { id: string; attachmentId: string; title: string | null; description: string; sortOrder: number; file: AttachmentFile }
export interface ServerTask {
  id: string; title: string | null; milestoneId: string | null; milestoneSnapshot: { id: string; name: string; isGeneral: boolean } | null; content: WorklogDocument;
  titlePreview: string; performedStart: string | null; performedEnd: string | null; sortOrder: number; attachments: ServerAttachmentUse[];
}
export interface ServerAchievement {
  id: string; type: 'quantitative' | 'qualitative'; presetKey: string; title: string | null; content: WorklogDocument | null;
  numericPayload: Record<string, unknown> | null; kpiId: string | null; kpiSnapshot: Record<string, unknown> | null;
  measuredOn: string | null; periodStart: string | null; periodEnd: string | null; sourceTaskId: string | null;
}
export interface TrackerRef {
  id: string; clientEntryId: string; trackerType: 'todo' | 'issue'; trackerId: string; hidden: boolean;
  originalSnapshot: { content: WorklogDocument; status?: string; dueDate?: string | null; assigneeName?: string | null };
  current: { status: string | null; deleted: boolean; dueDate?: string | null; assigneeId?: string | null };
}
export interface ServerLog {
  id: string; projectId: string; authorId: string; authorSnapshot: { name: string; teamName?: string } | null; workDate: string; revision: number;
  updatedAt: string; deletedAt: string | null; lessonLearned: WorklogDocument | null; note: WorklogDocument | null; tasks: ServerTask[];
  collaborators: { userId: string; name: string; team: string | null }[]; achievements: ServerAchievement[]; trackerRefs: TrackerRef[];
  trackerRefMap?: Record<string, { refId: string; trackerType: string; trackerId: string }>;
}
export interface TrackerBase {
  id: string; projectId: string; content: WorklogDocument; assigneeId: string | null; assigneeName: string | null; dueDate: string | null;
  status: string; overdue: boolean; revision: number; sourceLogId: string | null; events?: { id: string; previousStatus: string | null; nextStatus: string; resultText: string | null; occurredAt: string; createdTaskId: string | null }[];
}
export interface Todo extends TrackerBase { sourceIssueId: string | null }
export interface Issue extends TrackerBase { impact: WorklogDocument | null; response: WorklogDocument | null; responseTodoIds?: string[] }
export interface AppInfo { instanceId: string; restoreGeneration: number; schemaVersion: string; timezone: string; maxAttachmentBytes: number }
