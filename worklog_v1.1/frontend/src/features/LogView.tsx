import { useMemo } from 'react';
import { api } from '../api/client';
import type { ServerLog } from '../api/types';
import { RichEditor } from '../editor/RichEditor';
import type { ImageContextValue, ImageUse } from '../editor/context';
import { Modal, useAsync } from '../ui';

/** 다른 담당자(또는 내) 일지를 읽기 전용으로 본다. 수정은 작성 화면에서만 한다. */
export function LogView({ logId, onClose }: { logId: string; onClose: () => void }) {
  const { data: log, error } = useAsync(() => api.get<ServerLog>(`/logs/${logId}`), [logId]);
  return (
    <Modal title="업무일지 보기 (읽기 전용)" wide onClose={onClose}>
      {error && <p className="field-error">{error}</p>}
      {!log && !error && <p className="hint">불러오는 중…</p>}
      {log && (
        <>
          <p className="hint">
            {log.workDate} · {log.authorSnapshot?.name}{log.authorSnapshot?.teamName ? ` · ${log.authorSnapshot.teamName}` : ''} · revision {log.revision}
          </p>
          {log.tasks.map((t, i) => <TaskView key={t.id} index={i} task={t} />)}
          {log.trackerRefs.filter((r) => !r.hidden).length > 0 && (
            <div className="sub-card"><strong>등록한 To-Do / Issue</strong>
              {log.trackerRefs.filter((r) => !r.hidden).map((r) => (
                <p key={r.id}>{r.trackerType === 'todo' ? 'To-Do' : 'Issue'} · 현재 {r.current.deleted ? '삭제됨' : r.current.status}</p>
              ))}
            </div>
          )}
          {log.achievements.length > 0 && <p className="hint">성과 {log.achievements.length}건</p>}
        </>
      )}
    </Modal>
  );
}

function TaskView({ index, task }: { index: number; task: ServerLog['tasks'][number] }) {
  const images: ImageContextValue = useMemo(() => ({
    get: (id): ImageUse | undefined => {
      const a = task.attachments.find((x) => x.id === id);
      return a ? { useId: a.id, previewUrl: `/api/v1/attachments/${a.attachmentId}/content`, title: a.title ?? '', description: a.description, fileName: a.file.originalName } : undefined;
    },
    setMeta: () => {},
    upload: async () => { throw new Error('읽기 전용입니다.'); },
    errors: {},
  }), [task]);
  const docs = task.attachments.filter((a) => !a.file.isImage);
  return (
    <div className="sub-card">
      <strong>TASK {index + 1}{task.title ? `: ${task.title}` : ''} · {task.milestoneSnapshot?.name}</strong>
      <RichEditor docKey={`view-${task.id}`} value={task.content} images={images} editable={false} onChange={() => {}} />
      {docs.map((d) => <a key={d.id} className="chip" href={`/api/v1/attachments/${d.attachmentId}/content`}>{d.file.originalName}</a>)}
    </div>
  );
}
