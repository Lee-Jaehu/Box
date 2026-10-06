import { useMemo, useRef, useState } from 'react';
import { api } from '../api/client';
import type { Milestone, Project } from '../api/types';
import { RichEditor } from '../editor/RichEditor';
import type { ImageContextValue, ImageUse } from '../editor/context';
import { titlePreview } from '../editor/document';
import { uid, type DraftAttachment, type DraftTask } from '../drafts/logDraft';
import { errText, useToast } from '../ui';

interface Props {
  index: number;
  total: number;
  task: DraftTask;
  open: boolean;
  project: Project;
  milestones: Milestone[];
  errors: string[];
  imageErrors: Record<string, string | undefined>;
  onToggle: () => void;
  onChange: (patch: Partial<DraftTask>) => void;
  onMove: (dir: -1 | 1) => void;
  onCopy: () => void;
  onRemove: () => void;
  onAddMilestone: (name: string) => Promise<Milestone | null>;
}

const MAX_BYTES = 20 * 1024 * 1024;

export function TaskCard({ index, total, task, open, project, milestones, errors, imageErrors, onToggle, onChange, onMove, onCopy, onRemove, onAddMilestone }: Props) {
  const toast = useToast();
  const [quick, setQuick] = useState('');
  const [showDates, setShowDates] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const taskRef = useRef(task);
  taskRef.current = task;
  const preview = task.title.trim() || titlePreview(task.content.doc); // 이름이 있으면 이름, 없으면 본문 첫 줄

  const upload = async (file: File): Promise<DraftAttachment> => {
    if (file.size > MAX_BYTES) throw new Error(`'${file.name}'은(는) 파일당 20MB를 넘어 첨부할 수 없습니다.`);
    const form = new FormData();
    form.set('projectId', project.id);
    form.set('file', file);
    const att = await api.form<{ id: string; originalName: string; mediaType: string; isImage: boolean }>('/attachments', form);
    const use: DraftAttachment = { id: uid(), attachmentId: att.id, title: '', description: '', fileName: att.originalName, mediaType: att.mediaType, isImage: att.isImage };
    onChange({ attachments: [...taskRef.current.attachments, use] });
    taskRef.current = { ...taskRef.current, attachments: [...taskRef.current.attachments, use] };
    return use;
  };

  const images: ImageContextValue = useMemo(() => ({
    get: (id): ImageUse | undefined => {
      const a = task.attachments.find((x) => x.id === id);
      return a ? { useId: a.id, previewUrl: `/api/v1/attachments/${a.attachmentId}/content`, title: a.title, description: a.description, fileName: a.fileName } : undefined;
    },
    setMeta: (id, patch) => onChange({ attachments: taskRef.current.attachments.map((a) => (a.id === id ? { ...a, ...patch } : a)) }),
    upload: async (file) => {
      if (!file.type.startsWith('image/')) throw new Error('이미지 파일만 본문에 넣을 수 있습니다. 문서는 ‘문서 첨부’를 사용하세요.');
      const a = await upload(file);
      return { useId: a.id, previewUrl: `/api/v1/attachments/${a.attachmentId}/content`, title: '', description: '', fileName: a.fileName };
    },
    errors: imageErrors,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [task.attachments, imageErrors]);

  const docs = task.attachments.filter((a) => !a.isImage);
  const quickAdd = async () => {
    const m = await onAddMilestone(quick.trim());
    if (m) { onChange({ milestoneId: m.id }); setQuick(''); }
  };

  return (
    <section className={`task-card${errors.length ? ' invalid' : ''}`} aria-label={`TASK ${index + 1}`}>
      <header>
        <button type="button" className="link" onClick={onToggle} aria-expanded={open}>{open ? '▾' : '▸'} TASK {index + 1}</button>
        {!open && <span className="preview">{preview || '(내용 없음)'}</span>}
        <span className="grow" />
        <button type="button" disabled={index === 0} onClick={() => onMove(-1)} aria-label="위로">↑</button>
        <button type="button" disabled={index === total - 1} onClick={() => onMove(1)} aria-label="아래로">↓</button>
        <button type="button" onClick={onCopy} title="복사하면 새 TASK로 만들어지며 정식 저장 전 초안입니다">복사</button>
        <button type="button" onClick={() => { if (!preview || window.confirm('이 TASK를 삭제할까요? (서버 저장 전까지는 초안에서만 사라집니다)')) onRemove(); }}>삭제</button>
      </header>
      {open && (
        <div className="task-body">
          <label className="field">
            <span className="field-label">TASK 이름 (선택)</span>
            <input value={task.title} maxLength={200} placeholder="예: 검증 시나리오 정리 — 비워 두면 본문 첫 줄이 요약으로 쓰입니다" onChange={(e) => onChange({ title: e.target.value })} />
          </label>
          <div className="row">
            <label className="field">
              <span className="field-label">마일스톤</span>
              <select value={task.milestoneId} onChange={(e) => onChange({ milestoneId: e.target.value })}>
                <option value="">선택…</option>
                {milestones.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </label>
            <label className="field">
              <span className="field-label">새 마일스톤 (이름만 입력)</span>
              <span className="inline">
                <input value={quick} onChange={(e) => setQuick(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && quick.trim()) { e.preventDefault(); void quickAdd(); } }} placeholder="예: 시험 평가" />
                <button type="button" disabled={!quick.trim()} onClick={() => void quickAdd()}>추가</button>
              </span>
            </label>
            <button type="button" className="link" onClick={() => setShowDates((v) => !v)}>{showDates ? '수행 기간 접기' : '수행 기간 변경'}</button>
          </div>
          {showDates && (
            <div className="row">
              <label className="field"><span className="field-label">수행 시작</span><input type="date" value={task.performedStart ?? ''} onChange={(e) => onChange({ performedStart: e.target.value || null })} /></label>
              <label className="field"><span className="field-label">수행 종료</span><input type="date" value={task.performedEnd ?? ''} onChange={(e) => onChange({ performedEnd: e.target.value || null })} /></label>
              <small className="hint">기본값은 업무 날짜입니다. 다른 TASK와 기간이 겹쳐도 됩니다.</small>
            </div>
          )}
          <RichEditor docKey={task.id} value={task.content} images={images} placeholder={`TASK ${index + 1} 내용`}
            onChange={(doc) => onChange({ content: doc })} />
          <div className="attachments">
            <button type="button" onClick={() => fileRef.current?.click()}>문서 첨부</button>
            <input ref={fileRef} type="file" hidden multiple accept=".pdf,.xlsx,.csv,.docx,.pptx,.txt"
              onChange={(e) => {
                const files = [...(e.target.files ?? [])];
                e.target.value = '';
                void (async () => { for (const f of files) { try { await upload(f); } catch (err) { toast('err', errText(err)); } } })();
              }} />
            <small className="hint">파일당 20MB · PDF/XLSX/CSV/DOCX/PPTX/TXT (이미지는 편집기의 ‘이미지’ 버튼)</small>
            {docs.map((d) => (
              <span key={d.id} className="chip">
                {d.fileName}
                <button type="button" aria-label={`${d.fileName} 제거`} onClick={() => onChange({ attachments: task.attachments.filter((x) => x.id !== d.id) })}>×</button>
              </span>
            ))}
          </div>
          {errors.map((m) => <p key={m} className="field-error">{m}</p>)}
        </div>
      )}
    </section>
  );
}
