import { describe, expect, it } from 'vitest';
import { MemoryDraftStore } from './store';
import {
  draftFromServer, draftKey, emptyDraft, isMeaningful, parseDraftKey, reconcileAfterSave, toSaveBody, validateDraft, type LogDraft,
} from './logDraft';
import type { ServerLog } from '../api/types';
import { wrapDocument } from '../editor/document';

const paragraph = (text: string) => wrapDocument({ type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] });
const serverLog = (revision: number, text = '서버'): ServerLog => ({
  id: 'L1', projectId: 'P', authorId: 'A', authorSnapshot: { name: '김하나' }, workDate: '2026-10-04', revision, updatedAt: '', deletedAt: null,
  lessonLearned: null, note: null, collaborators: [], achievements: [], trackerRefs: [],
  tasks: [{ id: 'T1', title: null, milestoneId: 'M', milestoneSnapshot: { id: 'M', name: '일반', isGeneral: true }, content: paragraph(text), titlePreview: text,
    performedStart: '2026-10-04', performedEnd: '2026-10-04', sortOrder: 0, attachments: [] }],
});

describe('draft key', () => {
  it('includes instance, restore generation, actor, project and date so drafts never mix', () => {
    const a = draftKey({ instanceId: 'i', generation: 0, actorId: 'u1', projectId: 'p1', date: '2026-10-04' });
    const b = draftKey({ instanceId: 'i', generation: 0, actorId: 'u2', projectId: 'p1', date: '2026-10-04' });
    const c = draftKey({ instanceId: 'i', generation: 1, actorId: 'u1', projectId: 'p1', date: '2026-10-04' });
    expect(new Set([a, b, c]).size).toBe(3);
    expect(parseDraftKey(a)).toEqual({ instanceId: 'i', generation: 0, actorId: 'u1', projectId: 'p1', date: '2026-10-04' });
  });

  it('memory store lists by prefix (used to find stale-generation drafts)', async () => {
    const s = new MemoryDraftStore();
    const d = emptyDraft('M', '2026-10-04');
    await s.put({ key: 'i|0|u1|p1|2026-10-04', draft: d, updatedAt: '' });
    await s.put({ key: 'i|1|u1|p1|2026-10-04', draft: d, updatedAt: '' });
    await s.put({ key: 'i|0|u2|p1|2026-10-04', draft: d, updatedAt: '' });
    expect((await s.listPrefix('i|')).length).toBe(3);
    expect((await s.listPrefix('i|0|u1|')).length).toBe(1);
  });
});

describe('save body', () => {
  it('TASK name is optional: blank/whitespace becomes null, a real name is trimmed and survives server round trip', () => {
    const d = draftFromServer(serverLog(2));
    expect(d.tasks[0].title).toBe('');
    expect((toSaveBody(d) as { tasks: { title: string | null }[] }).tasks[0].title).toBeNull();
    d.tasks[0].title = '  검증 시나리오 정리 ';
    expect((toSaveBody(d) as { tasks: { title: string | null }[] }).tasks[0].title).toBe('검증 시나리오 정리');
    const withName = serverLog(3); withName.tasks[0].title = '서버 이름';
    expect(draftFromServer(withName).tasks[0].title).toBe('서버 이름');
  });

  it('sends client-generated ids and expectedRevision from the draft base', () => {
    const d = draftFromServer(serverLog(4));
    const body = toSaveBody(d) as { expectedRevision: number; tasks: { id: string }[] };
    expect(body.expectedRevision).toBe(4);
    expect(body.tasks[0].id).toBe('T1');
  });

  it('empty optional sections are not forced into the payload', () => {
    const d = emptyDraft('M', '2026-10-04');
    d.lesson = wrapDocument({ type: 'doc', content: [{ type: 'paragraph' }] });
    const body = toSaveBody(d) as { lessonLearned: unknown; note: unknown; achievements: unknown[] };
    expect(body.lessonLearned).toBeNull();
    expect(body.note).toBeNull();
    expect(body.achievements).toEqual([]);
  });
});

describe('reconcile after save (no draft loss while saving)', () => {
  const sentBody = { newTodos: [{ clientEntryId: 'e1' }], newIssues: [], hiddenTrackerRefIds: [] };

  it('rebuilds from the server when nothing changed during the save', () => {
    const d: LogDraft = { ...draftFromServer(serverLog(1)), version: 5 };
    const out = reconcileAfterSave(d, 5, sentBody, serverLog(2, '저장됨'));
    expect(out.baseRevision).toBe(2);
    expect(out.tasks[0].content.doc.content?.[0].content?.[0].text).toBe('저장됨');
  });

  it('keeps newer local input typed during the save, only moving base revision forward', () => {
    const d: LogDraft = { ...draftFromServer(serverLog(1)), version: 5 };
    const typedDuringSave: LogDraft = {
      ...d, version: 7, tasks: [{ ...d.tasks[0], content: paragraph('저장 중에 더 입력한 내용') }],
      newTodos: [{ clientEntryId: 'e1', content: paragraph('등록됨'), assigneeId: null, dueDate: null }, { clientEntryId: 'e2', content: paragraph('새로 추가'), assigneeId: null, dueDate: null }],
    };
    const out = reconcileAfterSave(typedDuringSave, 5, sentBody, serverLog(2, '이전 응답'));
    expect(out.tasks[0].content.doc.content?.[0].content?.[0].text).toBe('저장 중에 더 입력한 내용'); // 이전 응답으로 덮이지 않음
    expect(out.baseRevision).toBe(2);
    expect(out.newTodos.map((n) => n.clientEntryId)).toEqual(['e2']);                               // 이미 등록된 항목만 제거
  });
});

describe('client validation', () => {
  it('requires task content, milestone and image descriptions', () => {
    const d = emptyDraft('', '2026-10-04');
    expect(validateDraft(d).map((i) => i.path)).toEqual(['tasks[0].content', 'tasks[0].milestoneId']);
    d.tasks[0].milestoneId = 'M';
    d.tasks[0].content = wrapDocument({ type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: '본문' }] }, { type: 'image', attrs: { attachmentUseId: 'U1' } }] });
    d.tasks[0].attachments = [{ id: 'U1', attachmentId: 'A', title: '', description: ' ', fileName: 'a.png', mediaType: 'image/png', isImage: true }];
    expect(validateDraft(d).some((i) => i.message.includes('이미지 상세 설명'))).toBe(true);
    d.tasks[0].attachments[0].description = '오류 화면';
    expect(validateDraft(d)).toEqual([]);
  });

  it('empty draft is not meaningful and is not stored', () => {
    expect(isMeaningful(emptyDraft('M', '2026-10-04'))).toBe(false);
    const d = emptyDraft('M', '2026-10-04');
    d.tasks[0].content = paragraph('내용');
    expect(isMeaningful(d)).toBe(true);
  });
});
