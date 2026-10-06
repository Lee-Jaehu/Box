import { useMemo, useState } from 'react';
import { ApiException, api, newKey, qs } from '../api/client';
import type { Issue, List, Project, ServerLog, Todo, TrackerBase } from '../api/types';
import { draftKey } from '../drafts/logDraft';
import { isMeaningful } from '../drafts/logDraft';
import { draftStore } from '../drafts/store';
import { RichEditor } from '../editor/RichEditor';
import { emptyDocument, hasContent, titlePreview, type WorklogDocument } from '../editor/document';
import { Field, Modal, errText, fmtDate, todayLocal, useAsync, useSession, useToast } from '../ui';
import { ApplyButtons, useDraft } from './ProjectPicker';

type Kind = 'todo' | 'issue';
type Item = Todo | Issue;
const LABEL: Record<Kind, string> = { todo: 'To-Do', issue: 'Issue' };
const STATUS: Record<string, string> = { open: '열림', in_progress: '진행 중', completed: '완료', cancelled: '취소', resolved: '해결', closed: '종결' };
const DONE: Record<Kind, string> = { todo: 'completed', issue: 'resolved' };
const path = (kind: Kind) => (kind === 'todo' ? 'todos' : 'issues');

/** initialAssignee: Worklog 화면(PJT ▸ User ▸ Worklog)에서 그 사람 담당으로 시작. compact: Worklog 화면 안 패널용 (설명 문구 생략) */
export function TrackerPage({ kind, project, initialAssignee, compact = false }: { kind: Kind; project: Project; initialAssignee?: string; compact?: boolean }) {
  const toast = useToast();
  const { users } = useSession();
  const [applied, setApplied] = useState({ status: '', assignee: initialAssignee ?? '', onlyOpen: true }); // 조회에 쓰이는 필터
  const { draft, setDraft, dirty, apply } = useDraft(applied, setApplied); // 입력 중인 값: ‘필터 적용’으로 반영
  const { status, assignee, onlyOpen } = applied;
  const list = useAsync(() => api.get<List<Item>>(`/projects/${project.id}/${path(kind)}${qs({ status, assigneeId: assignee, limit: 200 })}`), [project.id, kind, status, assignee]);
  const [creating, setCreating] = useState(false);
  const [detail, setDetail] = useState<Item | null>(null);
  const [completing, setCompleting] = useState<Item | null>(null);
  const items = (list.data?.items ?? []).filter((i) => !onlyOpen || status || (kind === 'todo' ? ['open', 'in_progress'] : ['open', 'in_progress', 'resolved']).includes(i.status));

  const transition = async (i: Item, action: string) => {
    try {
      await api.post(`/${path(kind)}/${i.id}/${action}`, { expectedRevision: i.revision });
      list.reload();
      setDetail(null);
    } catch (e) { toast('err', errText(e)); list.reload(); }
  };

  return (
    <div className="stack">
      <div className="row between">
        <div className="row">
          <Field label="상태"><select value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value })}><option value="">전체</option>{(kind === 'todo' ? ['open', 'in_progress', 'completed', 'cancelled'] : ['open', 'in_progress', 'resolved', 'closed']).map((s) => <option key={s} value={s}>{STATUS[s]}</option>)}</select></Field>
          <Field label="담당자"><select value={draft.assignee} onChange={(e) => setDraft({ ...draft, assignee: e.target.value })}><option value="">전체</option>{users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></Field>
          <label className="check"><input type="checkbox" checked={draft.onlyOpen} onChange={(e) => setDraft({ ...draft, onlyOpen: e.target.checked })} /> 처리할 항목만</label>
          <ApplyButtons dirty={dirty} onApply={apply} onReset={() => { const d = { status: '', assignee: '', onlyOpen: true }; setDraft(d); setApplied(d); }} />
        </div>
        <button type="button" className="primary" onClick={() => setCreating(true)}>+ {LABEL[kind]} 등록</button>
      </div>
      {!compact && <p className="hint">{LABEL[kind]}는 프로젝트 단위의 현재 관리 상태입니다. 일별 TASK와 계속 연결되지 않으며, {kind === 'todo' ? '완료할 때' : '해결할 때'} 한 줄 결과를 오늘 한 일에 남길 수 있습니다.</p>}
      <table className="grid">
        <thead><tr><th>내용</th><th>담당</th><th>마감</th><th>상태</th><th /></tr></thead>
        <tbody>
          {items.map((i) => (
            <tr key={i.id} className={i.overdue ? 'bad' : ''}>
              <td><button type="button" className="link" onClick={() => setDetail(i)}>{titlePreview(i.content.doc, 80) || '(내용 없음)'}</button>
                {'sourceIssueId' in i && i.sourceIssueId && <span className="badge">Issue 대응</span>}{i.sourceLogId && <span className="badge">일지에서 등록</span>}</td>
              <td>{i.assigneeName ?? '—'}</td><td>{fmtDate(i.dueDate)}{i.overdue && <span className="badge bad">기한 초과</span>}</td><td>{STATUS[i.status]}</td>
              <td className="nowrap">
                {['open', 'in_progress'].includes(i.status) && <button type="button" onClick={() => setCompleting(i)}>{kind === 'todo' ? '완료' : '해결'}</button>}
                {kind === 'issue' && i.status === 'resolved' && <button type="button" onClick={() => void transition(i, 'close')}>종결</button>}
                {[DONE[kind], 'closed', 'cancelled'].includes(i.status) && <button type="button" onClick={() => void transition(i, 'reopen')}>다시 열기</button>}
              </td>
            </tr>
          ))}
          {list.data && items.length === 0 && <tr><td colSpan={5} className="hint">표시할 {LABEL[kind]}가 없습니다.</td></tr>}
        </tbody>
      </table>
      {creating && <CreateTracker kind={kind} project={project} onClose={() => setCreating(false)} onDone={() => { setCreating(false); list.reload(); }} />}
      {detail && <Detail kind={kind} item={detail} project={project} onClose={() => setDetail(null)} onChanged={() => { list.reload(); setDetail(null); }} />}
      {completing && <CompleteDialog kind={kind} item={completing} project={project} onClose={() => setCompleting(null)} onDone={() => { setCompleting(null); list.reload(); }} />}
    </div>
  );
}

function CreateTracker({ kind, project, onClose, onDone }: { kind: Kind; project: Project; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const { users } = useSession();
  const [content, setContent] = useState<WorklogDocument>(emptyDocument());
  const [impact, setImpact] = useState<WorklogDocument>(emptyDocument());
  const [response, setResponse] = useState<WorklogDocument>(emptyDocument());
  const [assignee, setAssignee] = useState('');
  const [due, setDue] = useState('');
  const [busy, setBusy] = useState(false);
  const [key] = useState(newKey());
  const submit = async () => {
    setBusy(true);
    try {
      await api.post(`/projects/${project.id}/${path(kind)}`, {
        content, assigneeId: assignee || null, dueDate: due || null,
        ...(kind === 'issue' ? { impact: hasContent(impact.doc) ? impact : null, response: hasContent(response.doc) ? response : null } : {}),
      }, { key });
      toast('ok', `${LABEL[kind]}를 등록했습니다.`);
      onDone();
    } catch (e) { toast('err', errText(e)); } finally { setBusy(false); }
  };
  return (
    <Modal title={`${LABEL[kind]} 등록`} wide onClose={onClose}>
      <Field label="내용 (필수)"><RichEditor docKey="create" value={content} images={null} onChange={setContent} /></Field>
      {kind === 'issue' && <><Field label="영향 (선택)"><RichEditor docKey="impact" value={impact} images={null} onChange={setImpact} /></Field>
        <Field label="대응 (선택)"><RichEditor docKey="resp" value={response} images={null} onChange={setResponse} /></Field></>}
      <div className="row">
        <Field label="담당자 (선택)"><select value={assignee} onChange={(e) => setAssignee(e.target.value)}><option value="">미지정</option>{users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></Field>
        <Field label="마감일 (선택)"><input type="date" value={due} onChange={(e) => setDue(e.target.value)} /></Field>
      </div>
      <div className="row end"><button type="button" onClick={onClose}>취소</button><button type="button" className="primary" disabled={busy || !hasContent(content.doc)} onClick={() => void submit()}>등록</button></div>
    </Modal>
  );
}

function Detail({ kind, item, project, onClose, onChanged }: { kind: Kind; item: Item; project: Project; onClose: () => void; onChanged: () => void }) {
  const toast = useToast();
  const { users } = useSession();
  const full = useAsync(() => api.get<Item>(`/${path(kind)}/${item.id}`), [item.id]);
  const cur = full.data ?? item;
  const [content, setContent] = useState<WorklogDocument | null>(null);
  const [assignee, setAssignee] = useState<string | null>(null);
  const [due, setDue] = useState<string | null>(null);
  const [respTodo, setRespTodo] = useState<WorklogDocument | null>(null);
  const save = async () => {
    try {
      await api.patch(`/${path(kind)}/${cur.id}`, {
        expectedRevision: cur.revision, ...(content ? { content } : {}),
        ...(assignee !== null ? (assignee ? { assigneeId: assignee } : { clearAssignee: true }) : {}),
        ...(due !== null ? (due ? { dueDate: due } : { clearDueDate: true }) : {}),
      });
      toast('ok', '저장했습니다.');
      onChanged();
    } catch (e) { toast('err', errText(e)); full.reload(); }
  };
  const status = async (s: 'open' | 'in_progress') => {
    try { await api.patch(`/${path(kind)}/${cur.id}`, { expectedRevision: cur.revision, status: s }); onChanged(); } catch (e) { toast('err', errText(e)); }
  };
  const remove = async () => {
    if (!window.confirm('휴지통으로 보낼까요? 출처 일지와 완료로 생성된 TASK는 그대로 유지됩니다.')) return;
    try { await api.del(`/${path(kind)}/${cur.id}?expectedRevision=${cur.revision}`); onChanged(); } catch (e) { toast('err', errText(e)); }
  };
  const addResponse = async () => {
    if (!respTodo) return;
    try {
      await api.post(`/issues/${cur.id}/todos`, { expectedIssueRevision: cur.revision, content: respTodo });
      toast('ok', '대응 To-Do를 만들었습니다. To-Do를 완료해도 Issue가 자동 해결되지는 않습니다.');
      setRespTodo(null);
      full.reload();
    } catch (e) { toast('err', errText(e)); }
  };
  const editable = ['open', 'in_progress'].includes(cur.status) || kind === 'issue';
  return (
    <Modal title={`${LABEL[kind]} 상세 · ${STATUS[cur.status]}`} wide onClose={onClose}>
      <Field label="내용"><RichEditor docKey={`d-${cur.id}-${cur.revision}`} value={content ?? cur.content} images={null} editable={editable} onChange={setContent} /></Field>
      <div className="row">
        <Field label="담당자"><select value={assignee ?? cur.assigneeId ?? ''} onChange={(e) => setAssignee(e.target.value)}><option value="">미지정</option>{users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></Field>
        <Field label="마감일"><input type="date" value={due ?? cur.dueDate ?? ''} onChange={(e) => setDue(e.target.value)} /></Field>
        <button type="button" className="primary" disabled={content === null && assignee === null && due === null} onClick={() => void save()}>변경 저장</button>
      </div>
      <div className="row">
        {['open', 'in_progress'].includes(cur.status) && <button type="button" onClick={() => void status(cur.status === 'open' ? 'in_progress' : 'open')}>{cur.status === 'open' ? '진행 중으로 표시' : '열림으로 되돌리기'}</button>}
        <button type="button" className="danger" onClick={() => void remove()}>휴지통으로 이동</button>
      </div>
      {kind === 'issue' && (
        <div className="card">
          <h4>대응 To-Do</h4>
          {((cur as Issue).responseTodoIds ?? []).length > 0 ? <p>연결된 To-Do {(cur as Issue).responseTodoIds!.length}개 — <a href={`#/todos/${project.id}`}>To-Do 탭에서 보기</a></p> : <p className="hint">모든 Issue에 To-Do가 필요한 것은 아닙니다.</p>}
          {respTodo ? (
            <>
              <RichEditor docKey={`rt-${cur.id}`} value={respTodo} images={null} onChange={setRespTodo} />
              <div className="row"><button type="button" className="primary" disabled={!hasContent(respTodo.doc)} onClick={() => void addResponse()}>대응 To-Do 만들기</button><button type="button" onClick={() => setRespTodo(null)}>취소</button></div>
            </>
          ) : <button type="button" onClick={() => setRespTodo(emptyDocument())}>+ 대응 할 일 추가</button>}
        </div>
      )}
      <h4>이력</h4>
      <ul className="refs">
        {(full.data?.events ?? []).map((e) => (
          <li key={e.id}><span className="badge">{STATUS[e.nextStatus] ?? e.nextStatus}</span><span className="grow">{e.resultText ?? ''}</span>
            <small className="hint">{new Date(e.occurredAt).toLocaleString('ko-KR')}{e.createdTaskId ? ' · 오늘 한 일에 기록됨' : ''}</small></li>
        ))}
        {(full.data?.events ?? []).length === 0 && <li className="hint">상태 변경 이력이 없습니다.</li>}
      </ul>
    </Modal>
  );
}

function CompleteDialog({ kind, item, project, onClose, onDone }: { kind: Kind; item: Item; project: Project; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const { users, actor, info } = useSession();
  const [result, setResult] = useState('');
  const [append, setAppend] = useState(false);
  const [date, setDate] = useState(todayLocal());
  const [author, setAuthor] = useState(actor?.id ?? '');
  const milestones = project.milestones ?? [];
  const [ms, setMs] = useState(milestones.find((m) => m.isGeneral)?.id ?? milestones[0]?.id ?? '');
  const [busy, setBusy] = useState(false);
  const [key] = useState(newKey());
  const target = useMemo(() => `${date} · ${users.find((u) => u.id === author)?.name ?? '작성자 미선택'} · ${milestones.find((m) => m.id === ms)?.name ?? ''}`, [date, author, ms, users, milestones]);
  const verb = kind === 'todo' ? '완료' : '해결';
  const submit = async () => {
    setBusy(true);
    try {
      let appendBody: Record<string, unknown> | null = null;
      if (append) {
        if (!author) throw new Error('일지 작성자를 선택해 주세요.');
        const logs = await api.get<List<ServerLog>>(`/projects/${project.id}/logs${qs({ date, authorId: author })}`);
        const log = logs.items[0];
        if (log?.deletedAt) throw new Error('같은 날짜의 일지가 휴지통에 있습니다. 휴지통에서 복원한 뒤 다시 시도해 주세요.');
        if (info) {
          const rec = await draftStore.get(draftKey({ instanceId: info.instanceId, generation: info.restoreGeneration, actorId: author, projectId: project.id, date }));
          if (rec && isMeaningful(rec.draft)) throw new Error('해당 날짜 일지에 저장되지 않은 초안이 있습니다. 먼저 일지 탭에서 저장하거나 초안을 정리한 뒤 다시 시도해 주세요.');
        }
        appendBody = { date, authorId: author, milestoneId: ms, expectedLogRevision: log?.revision ?? 0 };
      }
      await api.post(`/${path(kind)}/${item.id}/${kind === 'todo' ? 'complete' : 'resolve'}`, { expectedRevision: item.revision, resultText: result || null, appendToDailyLog: appendBody }, { key });
      toast('ok', append ? `${verb}했고 오늘 한 일에 결과를 남겼습니다.` : `${verb}했습니다.`);
      onDone();
    } catch (e) {
      toast('err', errText(e) + (e instanceof ApiException && e.code === 'REVISION_CONFLICT' ? ' 새로고침 후 다시 시도해 주세요.' : ''));
    } finally { setBusy(false); }
  };
  return (
    <Modal title={`${LABEL[kind]} ${verb}`} onClose={onClose}>
      <p><strong>{titlePreview(item.content.doc, 100)}</strong></p>
      <Field label="결과 (한 줄, 선택)"><input autoFocus value={result} onChange={(e) => setResult(e.target.value)} placeholder="예: 협력사 수정본 재검증 완료" /></Field>
      <label className="check"><input type="checkbox" checked={append} onChange={(e) => setAppend(e.target.checked)} /> 오늘 한 일에도 남기기 (일지에 TASK 추가)</label>
      {append && (
        <div className="sub-card">
          <div className="row">
            <Field label="날짜"><input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
            <Field label="작성자"><select value={author} onChange={(e) => setAuthor(e.target.value)}><option value="">선택…</option>{users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></Field>
            <Field label="마일스톤"><select value={ms} onChange={(e) => setMs(e.target.value)}>{milestones.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></Field>
          </div>
          <p className="hint">저장 대상: <strong>{target}</strong> 일지에 결과 TASK가 추가됩니다(일지가 없으면 새로 만듭니다). 상태 변경과 함께 한 번에 저장되며, 하나라도 실패하면 모두 취소됩니다.</p>
          {!result.trim() && <p className="field-error">일지에 남기려면 결과를 입력해 주세요.</p>}
        </div>
      )}
      <div className="row end"><button type="button" onClick={onClose}>취소</button>
        <button type="button" className="primary" disabled={busy || (append && !result.trim())} onClick={() => void submit()}>{verb}</button></div>
    </Modal>
  );
}

export type { TrackerBase };
