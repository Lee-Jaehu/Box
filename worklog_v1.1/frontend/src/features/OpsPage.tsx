import { useState } from 'react';
import { api } from '../api/client';
import { Field, Modal, errText, useAsync, useToast } from '../ui';

interface TrashItem { entityType: string; id: string; title: string; projectId: string; deletedAt: string }
interface ExportItem {
  targetKey: string; kind: string; projectName: string | null; date: string | null; relativePath: string; requestedRevision: number;
  exportedRevision: number; status: string; attempts: number; lastError: string | null; lagging: boolean; updatedAt: string | null;
}
interface ExportStatus { items: ExportItem[]; pendingCount: number; failedCount: number; dailyCount: number; jsonDir: string }
const EXPORT_KIND: Record<string, string> = { daily: '업무일지', project: '프로젝트', trackers: 'To-Do/Issue', master: '조직·사용자' };
interface BackupItem { id: string; kind: string; status: string; finishedAt: string | null; localDate: string | null; error: string | null; attachmentCount: number | null }
const KIND: Record<string, string> = { project: '프로젝트', milestone: '마일스톤', log: '일지', todo: 'To-Do', issue: 'Issue' };

export function OpsPage() {
  return (
    <section className="stack">
      <h2>운영</h2>
      <Trash />
      <Exports />
      <Backups />
    </section>
  );
}

function Trash() {
  const toast = useToast();
  const { data, reload } = useAsync(() => api.get<{ items: TrashItem[] }>('/trash'), []);
  const restore = async (t: TrashItem) => {
    try { await api.post(`/trash/${t.entityType}/${t.id}/restore`); toast('ok', '복원했습니다.'); reload(); } catch (e) { toast('err', errText(e)); }
  };
  return (
    <div className="card">
      <h3>휴지통</h3>
      <p className="hint">자동으로 영구 삭제되지 않습니다. 프로젝트를 삭제하면 하위 기록은 개별로 삭제되지 않고 함께 숨겨졌다가, 복원하면 원래 상태로 돌아옵니다.</p>
      <table className="grid">
        <tbody>
          {(data?.items ?? []).map((t) => (
            <tr key={t.id}><td>{KIND[t.entityType] ?? t.entityType}</td><td>{t.title}</td><td>{new Date(t.deletedAt).toLocaleString('ko-KR')}</td><td><button type="button" onClick={() => void restore(t)}>복원</button></td></tr>
          ))}
          {data && data.items.length === 0 && <tr><td className="hint">휴지통이 비어 있습니다.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function Exports() {
  const toast = useToast();
  const { data, reload } = useAsync(() => api.get<ExportStatus>('/exports/status'), []);
  const [showAll, setShowAll] = useState(true);
  const rebuild = async () => {
    try { await api.post('/exports/rebuild', { all: true }); toast('ok', 'JSON 사본 전체 재생성을 요청했습니다. 잠시 뒤 새로고침하세요.'); reload(); } catch (e) { toast('err', errText(e)); }
  };
  const items = data?.items ?? [];
  const rows = (showAll ? items : items.filter((i) => i.lagging || i.status === 'failed'))
    .slice().sort((a, b) => (a.kind === b.kind ? (b.date ?? '').localeCompare(a.date ?? '') : a.kind.localeCompare(b.kind)));
  const stateLabel = (i: ExportItem) => (i.status === 'failed' ? '실패(재시도 대기)' : i.lagging ? '대기 중' : '완료');
  return (
    <div className="card">
      <h3>JSON 사본</h3>
      <p className="hint">SQLite가 원본이고 JSON은 저장할 때마다 자동으로 만들어지는 읽기용 사본입니다. 사본을 직접 고쳐도 DB에 반영되지 않습니다. 저장 성공과 사본 갱신은 별개이며 보통 1~2초 안에 따라옵니다.</p>
      {data && <p><strong>저장 위치:</strong> <code>{data.jsonDir}</code><br /><small className="hint">업무일지는 <code>projects\&lt;프로젝트 ID&gt;\&lt;날짜&gt;\daily.json</code> 에 날짜별로 생성됩니다. 이 서버가 사용하는 데이터 폴더의 json 폴더이며, 테스트 실행(<code>테스트실행.bat</code>)은 <code>data_test</code> 를 따로 씁니다.</small></p>}
      <p>
        업무일지 사본 {data?.dailyCount ?? 0}건 · 대기 {data?.pendingCount ?? 0}건 · 실패 {data?.failedCount ?? 0}건{' '}
        <button type="button" onClick={reload}>새로고침</button> <button type="button" onClick={() => void rebuild()}>전체 재생성 요청</button>{' '}
        <label className="check"><input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> 완료된 항목도 보기</label>
      </p>
      {data && data.dailyCount === 0 && <p className="notice">아직 이 서버의 DB에 저장된 업무일지가 없어 업무일지 JSON도 없습니다. 일지를 저장하면 여기에 나타납니다.</p>}
      {rows.length > 0 && (
        <table className="grid">
          <thead><tr><th>종류</th><th>프로젝트</th><th>날짜</th><th>파일 (json 폴더 기준)</th><th>상태</th><th>마지막 갱신</th><th>오류</th></tr></thead>
          <tbody>{rows.map((i) => (
            <tr key={i.targetKey} className={i.status === 'failed' ? 'bad' : i.lagging ? 'bad-soft' : ''}>
              <td>{EXPORT_KIND[i.kind] ?? i.kind}</td><td>{i.projectName ?? '—'}</td><td>{i.date ?? '—'}</td>
              <td><code>{i.relativePath}</code></td><td>{stateLabel(i)}{i.attempts > 0 ? ` (${i.attempts}회 시도)` : ''}</td>
              <td>{i.updatedAt ? new Date(i.updatedAt).toLocaleString('ko-KR') : '—'}</td><td>{i.lastError ?? ''}</td>
            </tr>))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Backups() {
  const toast = useToast();
  const { data, reload } = useAsync(() => api.get<{ items: BackupItem[] }>('/backups'), []);
  const [restoring, setRestoring] = useState<BackupItem | null>(null);
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  const now = async () => {
    setBusy(true);
    try { await api.post('/backups'); toast('ok', '백업을 만들었습니다.'); reload(); } catch (e) { toast('err', errText(e)); } finally { setBusy(false); }
  };
  const restore = async () => {
    if (!restoring) return;
    setBusy(true);
    try {
      await api.post(`/backups/${restoring.id}/restore`, { confirm: 'RESTORE' });
      toast('ok', '복원했습니다. 화면을 새로고침합니다.');
      setTimeout(() => window.location.reload(), 800);
    } catch (e) { toast('err', errText(e)); } finally { setBusy(false); setRestoring(null); }
  };
  return (
    <div className="card">
      <h3>백업</h3>
      <p className="hint">실행 중 하루 첫 저장 이후 자동으로 예약되며, 성공한 최근 14개를 보관합니다. 같은 디스크의 백업은 디스크 고장을 막아주지 않으니 설정에서 별도 드라이브 경로를 지정할 수 있습니다.</p>
      <button type="button" className="primary" disabled={busy} onClick={() => void now()}>지금 백업</button>
      <table className="grid">
        <thead><tr><th>종류</th><th>상태</th><th>완료 시각</th><th>첨부</th><th /></tr></thead>
        <tbody>
          {(data?.items ?? []).map((b) => (
            <tr key={b.id}><td>{{ daily: '자동(일일)', manual: '수동', pre_restore: '복원 직전' }[b.kind] ?? b.kind}</td>
              <td>{{ succeeded: '성공', failed: '실패', scheduled: '예약됨', running: '진행 중' }[b.status] ?? b.status}{b.error ? ` — ${b.error}` : ''}</td>
              <td>{b.finishedAt ? new Date(b.finishedAt).toLocaleString('ko-KR') : '—'}</td><td>{b.attachmentCount ?? '—'}</td>
              <td>{b.status === 'succeeded' && <button type="button" onClick={() => { setTyped(''); setRestoring(b); }}>복원…</button>}</td></tr>
          ))}
        </tbody>
      </table>
      {restoring && (
        <Modal title="백업에서 복원" onClose={() => setRestoring(null)}>
          <p className="field-error">복원하면 현재 DB와 첨부가 이 백업 시점으로 되돌아갑니다. 진행 전에 현재 상태를 ‘복원 직전’ 백업으로 한 번 더 보관하며, 복원 중에는 저장이 잠시 막힙니다. 다른 사용자의 브라우저 임시저장 초안은 복원 이전 데이터 기준이라 자동 저장되지 않습니다.</p>
          <Field label="계속하려면 ‘복원’이라고 입력하세요"><input value={typed} onChange={(e) => setTyped(e.target.value)} /></Field>
          <div className="row end"><button type="button" onClick={() => setRestoring(null)}>취소</button><button type="button" className="danger" disabled={typed !== '복원' || busy} onClick={() => void restore()}>복원 실행</button></div>
        </Modal>
      )}
    </div>
  );
}
