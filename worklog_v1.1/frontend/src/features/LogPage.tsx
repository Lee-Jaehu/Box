import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ApiException, api, newKey, qs } from '../api/client';
import type { List, Milestone, Project, ServerLog } from '../api/types';
import {
  draftFromServer, draftKey, emptyDraft, isMeaningful, newTask, parseDraftKey, reconcileAfterSave, toSaveBody, uid, validateDraft,
  type ClientIssue, type DraftTask, type LogDraft,
} from '../drafts/logDraft';
import { draftStore, type DraftRecord } from '../drafts/store';
import { RichEditor } from '../editor/RichEditor';
import { emptyDocument, titlePreview } from '../editor/document';
import { Field, Modal, errText, todayLocal, useSession, useToast } from '../ui';
import { AchievementList, Collaborators, NewTrackerList, TrackerRefs } from './LogSections';
import { TaskCard } from './TaskCard';

interface Props { project: Project; reloadProject: () => void; initialDate?: string }
type Banner =
  | { kind: 'restored' }
  | { kind: 'candidate'; record: DraftRecord }
  | { kind: 'stale'; record: DraftRecord }
  | { kind: 'trash'; logId: string }
  | { kind: 'conflict'; latest: ServerLog }
  | null;

const fmtTime = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString('ko-KR', { hour12: false }) : '');

function plainText(d: LogDraft): string {
  return d.tasks.map((t, i) => `[TASK ${i + 1}${t.title.trim() ? `: ${t.title.trim()}` : ''}]\n${titlePreview(t.content.doc, 100000)}`).join('\n\n');
}

export function LogPage({ project, reloadProject, initialDate }: Props) {
  const toast = useToast();
  const { actor, info, users } = useSession();
  const [date, setDate] = useState(initialDate || todayLocal());
  useEffect(() => { window.history.replaceState(null, '', `#/logs/${project.id}/${date}`); }, [date, project.id]); // 새로고침해도 같은 일지로 돌아오도록 주소 유지
  const milestones: Milestone[] = project.milestones ?? [];
  const general = milestones.find((m) => m.isGeneral) ?? milestones[0];
  const lastMilestone = useRef<string>(general?.id ?? '');

  const [loading, setLoading] = useState(true);
  const [server, setServer] = useState<ServerLog | null>(null);
  const [draft, setDraft] = useState<LogDraft>(() => emptyDraft(general?.id ?? '', date));
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const [loaded, setLoaded] = useState(false);
  const [banner, setBanner] = useState<Banner>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [localSavedAt, setLocalSavedAt] = useState<string | null>(null);
  const [serverSavedAt, setServerSavedAt] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [issues, setIssues] = useState<ClientIssue[]>([]);
  const [imageErrors, setImageErrors] = useState<Record<string, string | undefined>>({});
  const [archived, setArchived] = useState<DraftRecord[]>([]);
  const [view, setView] = useState<ServerLog | DraftRecord | null>(null);
  const [sections, setSections] = useState<Set<string>>(new Set());
  const [others, setOthers] = useState<ServerLog[]>([]);
  const keyRef = useRef<string | null>(null);
  const retryKey = useRef<{ hash: string; key: string } | null>(null);

  const key = useMemo(() => (info && actor ? draftKey({ instanceId: info.instanceId, generation: info.restoreGeneration, actorId: actor.id, projectId: project.id, date }) : null), [info, actor, project.id, date]);
  keyRef.current = key;
  const isPlayable = !!actor && project.deletedAt == null;

  const update = useCallback((fn: (d: LogDraft) => LogDraft) => {
    setDraft((d) => ({ ...fn(d), version: d.version + 1 }));
  }, []);

  const persist = useCallback(async (k: string, d: LogDraft) => {
    if (isMeaningful(d)) {
      const rec: DraftRecord = { key: k, draft: { ...d, savedAt: new Date().toISOString() }, updatedAt: new Date().toISOString() };
      await draftStore.put(rec);
      setLocalSavedAt(rec.updatedAt);
    } else {
      await draftStore.delete(k);
      setLocalSavedAt(null);
    }
  }, []);

  // ── 불러오기: 서버 일지 + 브라우저 초안 (자동 덮어쓰기 없음) ──
  useEffect(() => {
    if (!key || !actor || !info) { setLoading(false); setLoaded(false); return; }
    let alive = true;
    const myKey = key;
    setLoading(true);
    setLoaded(false);
    setBanner(null);
    setIssues([]);
    setImageErrors({});
    void (async () => {
      try {
        const list = await api.get<List<ServerLog>>(`/projects/${project.id}/logs${qs({ date, authorId: actor.id })}`);
        const sl = list.items[0] ?? null;
        const rec = await draftStore.get(myKey);
        const all = await draftStore.listPrefix(`${info.instanceId}|`);
        const stale = all.find((r) => { const p = parseDraftKey(r.key); return p && p.generation < info.restoreGeneration && p.actorId === actor.id && p.projectId === project.id && p.date === date && isMeaningful(r.draft); });
        const arch = (await draftStore.listPrefix(`${myKey}#conflict-`));
        const day = await api.get<List<ServerLog>>(`/projects/${project.id}/logs${qs({ date })}`).catch(() => null);
        if (!alive) return;
        setArchived(arch);
        setOthers((day?.items ?? []).filter((l) => l.authorId !== actor.id && !l.deletedAt));
        const serverRev = sl && !sl.deletedAt ? sl.revision : 0;
        setServer(sl);
        const base = sl && !sl.deletedAt ? draftFromServer(sl) : emptyDraft(lastMilestone.current || general?.id || '', date);
        let chosen = base;
        let b: Banner = null;
        if (sl?.deletedAt) b = { kind: 'trash', logId: sl.id };
        else if (rec && isMeaningful(rec.draft)) {
          if (rec.draft.baseRevision === serverRev) { chosen = rec.draft; b = { kind: 'restored' }; }
          else b = { kind: 'candidate', record: rec };
        } else if (stale) b = { kind: 'stale', record: stale };
        setDraft(chosen);
        setOpen(new Set(chosen.tasks.map((t) => t.id).slice(0, 3)));
        setSections(new Set([
          ...(chosen.newTodos.length ? ['todo'] : []), ...(chosen.newIssues.length ? ['issue'] : []), ...(chosen.achievements.length ? ['achv'] : []),
          ...(chosen.lesson ? ['lesson'] : []), ...(chosen.note ? ['note'] : []), ...(chosen.collaboratorIds.length ? ['collab'] : []),
        ]));
        setBanner(b);
        setLocalSavedAt(rec?.updatedAt ?? null);
        setServerSavedAt(sl && !sl.deletedAt ? sl.updatedAt : null);
        setLoaded(true);
      } catch (e) {
        if (alive) toast('err', errText(e));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
      // 날짜/프로젝트/작성자를 바꾸기 전에 초안을 즉시 보관한다
      const d = draftRef.current;
      if (d.version > 0 && isMeaningful(d)) void draftStore.put({ key: myKey, draft: d, updatedAt: new Date().toISOString() });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, project.id]);

  // ── 자동 임시저장 (브라우저 IndexedDB, 서버 저장과 구별) ──
  useEffect(() => {
    if (!loaded || !key || draft.version === 0) return;
    const t = setTimeout(() => { void persist(key, draftRef.current); }, 1000);
    return () => clearTimeout(t);
  }, [draft.version, loaded, key, persist]);

  useEffect(() => {
    const flush = () => { const k = keyRef.current; const d = draftRef.current; if (k && d.version > 0 && isMeaningful(d)) void draftStore.put({ key: k, draft: d, updatedAt: new Date().toISOString() }); };
    window.addEventListener('pagehide', flush);
    return () => window.removeEventListener('pagehide', flush);
  }, []);

  const dirty = draft.version > 0;

  const addMilestone = async (name: string): Promise<Milestone | null> => {
    try {
      const m = await api.post<Milestone>(`/projects/${project.id}/milestones`, { name });
      if (m.similarNames?.length) toast('ok', `비슷한 이름이 있습니다: ${m.similarNames.join(', ')} (자동으로 합치지 않았습니다)`);
      reloadProject();
      return m;
    } catch (e) { toast('err', errText(e)); return null; }
  };

  const mapFieldErrors = (e: ApiException, d: LogDraft) => {
    const img: Record<string, string> = {};
    const out: ClientIssue[] = [];
    for (const fe of e.fieldErrors) {
      const m = /^tasks\[(\d+)\]\.attachments\[(\d+)\]\.description$/.exec(fe.field);
      if (m) { const id = d.tasks[Number(m[1])]?.attachments[Number(m[2])]?.id; if (id) img[id] = fe.message; }
      out.push({ path: fe.field, message: `${fe.field.replace(/\[(\d+)\]/g, (_, n) => ` ${Number(n) + 1}`)}: ${fe.message}` });
    }
    setImageErrors(img);
    setIssues(out);
  };

  const save = async () => {
    if (!actor || !key) return;
    const d = draftRef.current;
    const local = validateDraft(d);
    const imgLocal: Record<string, string> = {};
    d.tasks.forEach((t) => t.attachments.forEach((a) => { if (a.isImage && !a.description.trim()) imgLocal[a.id] = '이미지 상세 설명을 입력해 주세요.'; }));
    setImageErrors(imgLocal);
    setIssues(local);
    if (local.length) { toast('err', '입력 내용을 확인해 주세요.'); return; }
    const sentVersion = d.version;
    const body = toSaveBody(d) as { newTodos: { clientEntryId: string }[]; newIssues: { clientEntryId: string }[]; hiddenTrackerRefIds: string[] };
    const hash = JSON.stringify(body);
    if (!retryKey.current || retryKey.current.hash !== hash) retryKey.current = { hash, key: newKey() };  // 같은 내용 재시도는 같은 키(멱등)
    setSaving(true);
    try {
      await persist(key, d);
      const log = await api.put<ServerLog>(`/projects/${project.id}/logs/${date}/${actor.id}`, body, { key: retryKey.current.key });
      retryKey.current = null;
      setServer(log);
      setServerSavedAt(log.updatedAt);
      const next = reconcileAfterSave(draftRef.current, sentVersion, body, log);
      setDraft(next);
      setBanner(null);
      setIssues([]);
      setImageErrors({});
      if (next.version === 0) { await draftStore.delete(key); setLocalSavedAt(null); } else await persist(key, next);
      toast('ok', `서버에 저장했습니다 (revision ${log.revision}).`);
      reloadProject();
    } catch (e) {
      if (e instanceof ApiException) {
        if (e.code === 'REVISION_CONFLICT' || e.code === 'LOG_EXISTS') {
          const list = await api.get<List<ServerLog>>(`/projects/${project.id}/logs${qs({ date, authorId: actor.id })}`).catch(() => null);
          const latest = list?.items[0];
          if (latest) setBanner({ kind: 'conflict', latest });
          toast('err', '다른 곳에서 먼저 수정되었습니다. 내 입력은 그대로 보관되어 있습니다.');
        } else if (e.code === 'LOG_IN_TRASH') {
          setBanner({ kind: 'trash', logId: e.resourceId ?? '' });
        } else if (e.status === 422) {
          mapFieldErrors(e, d);
          toast('err', '입력 내용을 확인해 주세요.');
        } else toast('err', e.retryable ? `${e.message} (같은 내용으로 다시 저장하면 중복 없이 처리됩니다)` : e.message);
      } else toast('err', errText(e));
    } finally {
      setSaving(false);
    }
  };

  const useServerVersion = async (archiveCurrent: boolean) => {
    if (!actor || !key) return;
    const list = await api.get<List<ServerLog>>(`/projects/${project.id}/logs${qs({ date, authorId: actor.id })}`);
    const sl = list.items[0] ?? null;
    if (archiveCurrent && isMeaningful(draftRef.current)) {
      const rec: DraftRecord = { key: `${key}#conflict-${Date.now()}`, draft: draftRef.current, updatedAt: new Date().toISOString() };
      await draftStore.put(rec);
      setArchived((a) => [...a, rec]);
    }
    await draftStore.delete(key);
    setServer(sl);
    setServerSavedAt(sl && !sl.deletedAt ? sl.updatedAt : null);
    const base = sl && !sl.deletedAt ? draftFromServer(sl) : emptyDraft(lastMilestone.current, date);
    setDraft(base);
    setOpen(new Set(base.tasks.map((t) => t.id).slice(0, 3)));
    setBanner(null);
    setLocalSavedAt(null);
    setIssues([]);
  };

  // ── TASK 조작 ──
  const patchTask = (id: string, p: Partial<DraftTask>) => {
    if (p.milestoneId) lastMilestone.current = p.milestoneId;
    update((d) => ({ ...d, tasks: d.tasks.map((t) => (t.id === id ? { ...t, ...p } : t)) }));
  };
  const addTask = () => {
    const t = newTask(lastMilestone.current || general?.id || '', date);
    update((d) => ({ ...d, tasks: [...d.tasks, t] }));
    setOpen((o) => new Set(o).add(t.id));
  };
  const moveTask = (i: number, dir: -1 | 1) => update((d) => {
    const ts = [...d.tasks];
    const [x] = ts.splice(i, 1);
    ts.splice(i + dir, 0, x);
    return { ...d, tasks: ts };
  });
  const copyTask = (t: DraftTask) => {
    const copy: DraftTask = { ...t, id: uid(), performedStart: date, performedEnd: date, attachments: t.attachments.map((a) => ({ ...a, id: uid() })) };
    // 본문 image node 의 사용처 ID 도 새 ID 로 바꿔 서로 다른 설명을 가질 수 있게 한다(같은 바이너리 재사용)
    let json = JSON.stringify(copy.content);
    t.attachments.forEach((a, i) => { json = json.split(a.id).join(copy.attachments[i].id); });
    copy.content = JSON.parse(json);
    update((d) => { const idx = d.tasks.findIndex((x) => x.id === t.id); const ts = [...d.tasks]; ts.splice(idx + 1, 0, copy); return { ...d, tasks: ts }; });
    setOpen((o) => new Set(o).add(copy.id));
  };
  const removeTask = (id: string) => update((d) => ({ ...d, tasks: d.tasks.filter((t) => t.id !== id) }));
  const toggleSection = (k: string) => setSections((s) => new Set(s).add(k));

  if (!actor) return <p className="notice">상단에서 <strong>작성자</strong>를 먼저 선택해 주세요. (로그인이 아니라 기록에 표시되는 이름을 고르는 설정입니다)</p>;
  if (loading) return <p className="hint">불러오는 중…</p>;

  const taskIssues = (i: number) => issues.filter((x) => x.path.startsWith(`tasks[${i}]`)).map((x) => x.message);
  const otherIssues = issues.filter((x) => !x.path.startsWith('tasks['));

  return (
    <div className="stack">
      <div className="row log-head">
        <Field label="업무 날짜"><input type="date" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} /></Field>
        <Field label="작성자"><input value={`${actor.name}${actor.teamName ? ` · ${actor.teamName}` : ''}`} readOnly /></Field>
        <div className="save-state" aria-live="polite">
          <div>{server && !server.deletedAt ? <>서버 저장됨 {fmtTime(serverSavedAt)} · revision {server.revision}</> : '서버에는 아직 저장되지 않은 새 일지'}</div>
          <div className={dirty ? 'warn' : ''}>{dirty ? (localSavedAt ? `브라우저 임시저장 ${fmtTime(localSavedAt)} — 서버 저장 필요` : '변경됨 — 임시저장 중…') : '변경 사항 없음'}</div>
          {draftStore.degraded && <div className="field-error">이 브라우저에서는 임시저장을 쓸 수 없어 새로고침하면 사라질 수 있습니다.</div>}
        </div>
        <button type="button" className="primary" disabled={saving || !isPlayable || (!dirty && !!server && !server.deletedAt) || banner?.kind === 'trash'} onClick={() => void save()}>
          {saving ? '저장 중…' : '일지 저장'}
        </button>
      </div>

      {banner?.kind === 'restored' && <div className="notice">브라우저에 임시저장된 내용을 복구했습니다. 서버에는 아직 저장되지 않았습니다. <button type="button" onClick={() => void useServerVersion(true)}>버리고 서버본 보기 (초안은 보관)</button></div>}
      {banner?.kind === 'candidate' && (
        <div className="notice warn">
          이 날짜에 다른 시점 기준의 브라우저 임시저장 초안이 있습니다(서버가 그 뒤로 변경됨). 자동으로 덮어쓰지 않았습니다.{' '}
          <button type="button" onClick={() => setView(banner.record)}>초안 내용 보기/복사</button>{' '}
          <button type="button" onClick={() => { void draftStore.put({ ...banner.record, key: `${key}#conflict-${Date.now()}` }).then(() => draftStore.delete(key!)); setArchived((a) => [...a, banner.record]); setBanner(null); }}>보관함으로 이동</button>
        </div>
      )}
      {banner?.kind === 'stale' && (
        <div className="notice warn">
          서버가 백업에서 <strong>복원</strong>되기 전에 작성한 임시저장 초안이 있습니다. 이전 데이터 기준이라 자동 저장·서버 반영을 하지 않습니다.{' '}
          <button type="button" onClick={() => setView(banner.record)}>내용 확인/복사</button>{' '}
          <button type="button" onClick={() => { void draftStore.delete(banner.record.key); setBanner(null); }}>버리기</button>
        </div>
      )}
      {banner?.kind === 'trash' && (
        <div className="notice warn">같은 날짜의 일지가 휴지통에 있습니다. 새로 만들지 않고 복원해서 이어 쓰세요.{' '}
          <button type="button" className="primary" onClick={() => void api.post(`/trash/log/${banner.logId}/restore`).then(() => { toast('ok', '복원했습니다.'); setDate((d) => d + ''); void useServerVersion(false); }).catch((e) => toast('err', errText(e)))}>복원</button></div>
      )}
      {banner?.kind === 'conflict' && (
        <div className="notice warn" role="alert">
          <strong>다른 곳에서 먼저 수정되었습니다.</strong> 내 입력은 그대로 보관되어 있으며, 자동으로 병합하거나 덮어쓰지 않습니다.
          <div className="row">
            <button type="button" onClick={() => setView(banner.latest)}>최신본 보기</button>
            <button type="button" onClick={() => void navigator.clipboard.writeText(plainText(draftRef.current)).then(() => toast('ok', '내 내용을 복사했습니다.'))}>내 내용 복사</button>
            <button type="button" onClick={() => void useServerVersion(true)}>최신본 기준으로 다시 편집 (내 초안은 보관)</button>
          </div>
        </div>
      )}
      {archived.length > 0 && (
        <div className="notice">보관된 내 초안 {archived.length}개:{' '}
          {archived.map((r) => <span key={r.key}><button type="button" className="link" onClick={() => setView(r)}>{fmtTime(r.updatedAt)} 초안 보기</button>{' '}</span>)}
        </div>
      )}
      {otherIssues.length > 0 && <ul className="field-error">{otherIssues.map((x) => <li key={x.message}>{x.message}</li>)}</ul>}

      <h3>오늘 한 일</h3>
      {draft.tasks.map((t, i) => (
        <TaskCard key={t.id} index={i} total={draft.tasks.length} task={t} open={open.has(t.id)} project={project} milestones={milestones}
          errors={taskIssues(i)} imageErrors={imageErrors}
          onToggle={() => setOpen((o) => { const n = new Set(o); if (n.has(t.id)) n.delete(t.id); else n.add(t.id); return n; })}
          onChange={(p) => patchTask(t.id, p)} onMove={(dir) => moveTask(i, dir)} onCopy={() => copyTask(t)} onRemove={() => removeTask(t.id)} onAddMilestone={addMilestone} />
      ))}
      <button type="button" onClick={addTask} disabled={!isPlayable}>+ 다른 업무 기록</button>

      {server && <TrackerRefs refs={server.trackerRefs} projectId={project.id} hidden={draft.hiddenRefIds} onHide={(id) => update((d) => ({ ...d, hiddenRefIds: [...d.hiddenRefIds, id] }))} />}

      <div className="row add-sections">
        <span className="hint">필요할 때 추가:</span>
        {([['todo', '+ To-Do'], ['issue', '+ Issue'], ['achv', '+ 성과'], ['lesson', '+ Lesson Learned'], ['note', '+ 메모'], ['collab', '+ 협업자']] as [string, string][])
          .filter(([k]) => !sections.has(k)).map(([k, l]) => <button key={k} type="button" onClick={() => toggleSection(k)}>{l}</button>)}
      </div>
      {sections.has('todo') && <>
        <NewTrackerList kind="todo" items={draft.newTodos} users={users} onChange={(items) => update((d) => ({ ...d, newTodos: items }))} />
        <button type="button" onClick={() => update((d) => ({ ...d, newTodos: [...d.newTodos, { clientEntryId: uid(), content: emptyDocument(), assigneeId: null, dueDate: null }] }))}>+ To-Do 항목 추가</button></>}
      {sections.has('issue') && <>
        <NewTrackerList kind="issue" items={draft.newIssues} users={users} onChange={(items) => update((d) => ({ ...d, newIssues: items }))} />
        <button type="button" onClick={() => update((d) => ({ ...d, newIssues: [...d.newIssues, { clientEntryId: uid(), content: emptyDocument(), assigneeId: null, dueDate: null }] }))}>+ Issue 항목 추가</button></>}
      {sections.has('achv') && <AchievementList items={draft.achievements} kpis={project.kpis ?? []} today={date} onChange={(achievements) => update((d) => ({ ...d, achievements }))} />}
      {sections.has('lesson') && <div className="card"><h4>Lesson Learned</h4><RichEditor docKey={`lesson-${key}`} value={draft.lesson ?? emptyDocument()} images={null} onChange={(lesson) => update((d) => ({ ...d, lesson }))} /></div>}
      {sections.has('note') && <div className="card"><h4>메모</h4><RichEditor docKey={`note-${key}`} value={draft.note ?? emptyDocument()} images={null} onChange={(note) => update((d) => ({ ...d, note }))} /></div>}
      {sections.has('collab') && <Collaborators ids={draft.collaboratorIds} users={users} onChange={(ids) => update((d) => ({ ...d, collaboratorIds: ids }))} />}

      {others.length > 0 && (
        <div className="card">
          <h4>이 날짜에 다른 담당자가 쓴 일지 <small className="hint">읽기 전용입니다. 각자 독립된 일지이며 서로 덮어쓰지 않습니다.</small></h4>
          {others.map((l) => (
            <div key={l.id} className="sub-card">
              <strong>{l.authorSnapshot?.name}{l.authorSnapshot?.teamName ? ` · ${l.authorSnapshot.teamName}` : ''}</strong>{' '}
              <small className="hint">revision {l.revision} · {fmtTime(l.updatedAt)}</small>
              {l.tasks.map((t, i) => <p key={t.id}>TASK {i + 1} · {t.milestoneSnapshot?.name} — {t.titlePreview || '(내용 없음)'}</p>)}
            </div>
          ))}
        </div>
      )}

      <div className="row end sticky-save">
        <span className="hint">{dirty ? '서버에 저장해야 다른 사람이 볼 수 있습니다.' : ''}</span>
        <button type="button" className="primary" disabled={saving || !isPlayable || (!dirty && !!server && !server.deletedAt) || banner?.kind === 'trash'} onClick={() => void save()}>{saving ? '저장 중…' : '일지 저장'}</button>
      </div>

      {view && (
        <Modal title="내용 보기" wide onClose={() => setView(null)}>
          {'tasks' in view ? (
            <>
              <p className="hint">서버 최신본 · revision {(view as ServerLog).revision} · {(view as ServerLog).updatedAt}</p>
              {(view as ServerLog).tasks.map((t, i) => <div key={t.id} className="sub-card"><strong>TASK {i + 1}{t.title ? `: ${t.title}` : ''} · {t.milestoneSnapshot?.name}</strong><p>{t.titlePreview || '(내용 없음)'}</p></div>)}
            </>
          ) : (
            <>
              <p className="hint">브라우저 임시저장 초안 · {(view as DraftRecord).updatedAt}</p>
              <pre className="plain">{plainText((view as DraftRecord).draft)}</pre>
              <button type="button" onClick={() => void navigator.clipboard.writeText(plainText((view as DraftRecord).draft)).then(() => toast('ok', '복사했습니다.'))}>텍스트 복사</button>{' '}
              <button type="button" onClick={() => { const r = view as DraftRecord; void draftStore.delete(r.key); setArchived((a) => a.filter((x) => x.key !== r.key)); setView(null); if (banner && (banner.kind === 'stale' || banner.kind === 'candidate')) setBanner(null); }}>이 초안 삭제</button>
            </>
          )}
        </Modal>
      )}
    </div>
  );
}
