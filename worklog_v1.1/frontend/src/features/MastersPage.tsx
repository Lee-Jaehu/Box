import { useState } from 'react';
import { ApiException, api, newKey } from '../api/client';
import type { List, Org, User } from '../api/types';
import { Field, errText, useAsync, useSession, useToast } from '../ui';
import { ApplyButtons, onEnter, useDraft } from './ProjectPicker';

type Tab = 'orgs' | 'users' | 'import';

export function MastersPage() {
  const [tab, setTab] = useState<Tab>('users');
  return (
    <section>
      <h2>조직·사용자 기준정보</h2>
      <nav className="tabs">
        {([['users', '사용자'], ['orgs', '조직'], ['import', 'Excel/CSV 가져오기']] as [Tab, string][]).map(([k, l]) => (
          <button key={k} type="button" className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>{l}</button>
        ))}
      </nav>
      {tab === 'orgs' && <Orgs />}
      {tab === 'users' && <Users />}
      {tab === 'import' && <ImportWizard />}
    </section>
  );
}

function Orgs() {
  const toast = useToast();
  const { data, reload } = useAsync(() => api.get<List<Org>>('/organizations?limit=200'), []);
  const [name, setName] = useState('');
  const [kind, setKind] = useState<'division' | 'team'>('team');
  const [parent, setParent] = useState('');
  const orgs = data?.items ?? [];
  const divisions = orgs.filter((o) => o.kind === 'division');
  const add = async () => {
    try {
      await api.post('/organizations', { name, kind, parentId: kind === 'team' && parent ? parent : null });
      setName('');
      reload();
      toast('ok', '조직을 등록했습니다.');
    } catch (e) { toast('err', errText(e)); }
  };
  const toggle = async (o: Org) => {
    try { await api.patch(`/organizations/${o.id}`, { expectedRevision: o.revision, active: !o.active }); reload(); } catch (e) { toast('err', errText(e)); }
  };
  return (
    <div>
      <div className="row">
        <Field label="구분"><select value={kind} onChange={(e) => setKind(e.target.value as 'division' | 'team')}><option value="division">담당 조직</option><option value="team">팀</option></select></Field>
        {kind === 'team' && <Field label="상위 담당 조직"><select value={parent} onChange={(e) => setParent(e.target.value)}><option value="">없음</option>{divisions.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></Field>}
        <Field label="이름"><input value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <button type="button" className="primary" disabled={!name.trim()} onClick={() => void add()}>조직 등록</button>
      </div>
      <table className="grid">
        <thead><tr><th>구분</th><th>이름</th><th>상위</th><th>코드</th><th>상태</th><th /></tr></thead>
        <tbody>
          {orgs.map((o) => (
            <tr key={o.id} className={o.active ? '' : 'muted'}>
              <td>{o.kind === 'division' ? '담당 조직' : '팀'}</td><td>{o.name}</td>
              <td>{orgs.find((p) => p.id === o.parentId)?.name ?? '—'}</td><td>{o.externalKey ?? '—'}</td>
              <td>{o.active ? '사용' : '비활성'}</td>
              <td><button type="button" onClick={() => void toggle(o)}>{o.active ? '비활성화' : '활성화'}</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hint">조직은 참조 중일 수 있어 삭제하지 않고 비활성화합니다.</p>
    </div>
  );
}

function Users() {
  const toast = useToast();
  const { reloadUsers } = useSession();
  const orgs = useAsync(() => api.get<List<Org>>('/organizations?limit=200'), []);
  const [applied, setApplied] = useState({ teamId: '', q: '' }); // 조회에 쓰이는 필터
  const { draft: fd, setDraft: setFd, dirty: fDirty, apply: applyF } = useDraft(applied, setApplied); // 입력 중인 값: ‘필터 적용’으로 반영
  const teamFilter = applied.teamId;
  const q = applied.q;
  const { data, reload } = useAsync(() => api.get<List<User>>(`/users?limit=200${teamFilter ? `&teamId=${teamFilter}` : ''}${q ? `&q=${encodeURIComponent(q)}` : ''}`), [teamFilter, q]);
  const teams = (orgs.data?.items ?? []).filter((o) => o.kind === 'team' && o.active);
  const [form, setForm] = useState({ name: '', teamId: '', employeeNumber: '' });
  const add = async () => {
    try {
      await api.post('/users', { name: form.name, teamId: form.teamId, employeeNumber: form.employeeNumber || null });
      setForm({ name: '', teamId: form.teamId, employeeNumber: '' });
      reload();
      await reloadUsers();
      toast('ok', '사용자를 등록했습니다.');
    } catch (e) { toast('err', errText(e)); }
  };
  const toggle = async (u: User) => {
    try { await api.patch(`/users/${u.id}`, { expectedRevision: u.revision, active: !u.active }); reload(); await reloadUsers(); } catch (e) { toast('err', errText(e)); }
  };
  return (
    <div>
      <div className="row">
        <Field label="이름"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <Field label="팀"><select value={form.teamId} onChange={(e) => setForm({ ...form, teamId: e.target.value })}><option value="">선택…</option>{teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
        <Field label="사번 (선택)" hint="비워도 등록됩니다. 동명이인은 사번으로 구분합니다."><input value={form.employeeNumber} onChange={(e) => setForm({ ...form, employeeNumber: e.target.value })} /></Field>
        <button type="button" className="primary" disabled={!form.name.trim() || !form.teamId} onClick={() => void add()}>사용자 등록</button>
      </div>
      <div className="row">
        <Field label="팀 필터"><select value={fd.teamId} onChange={(e) => setFd({ ...fd, teamId: e.target.value })}><option value="">전체</option>{teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
        <Field label="이름/사번 검색"><input value={fd.q} onChange={(e) => setFd({ ...fd, q: e.target.value })} onKeyDown={onEnter(applyF)} placeholder="Enter로 적용" /></Field>
        <ApplyButtons dirty={fDirty} onApply={applyF} onReset={() => { const e = { teamId: '', q: '' }; setFd(e); setApplied(e); }} />
      </div>
      <table className="grid">
        <thead><tr><th>이름</th><th>팀</th><th>사번</th><th>상태</th><th /></tr></thead>
        <tbody>
          {(data?.items ?? []).map((u) => (
            <tr key={u.id} className={u.active ? '' : 'muted'}>
              <td>{u.name}</td><td>{u.divisionName ? `${u.divisionName} / ` : ''}{u.teamName}</td><td>{u.employeeNumber ?? '—'}</td><td>{u.active ? '사용' : '비활성'}</td>
              <td><button type="button" onClick={() => void toggle(u)}>{u.active ? '비활성화' : '활성화'}</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface PreviewRow { row: number; action: string; errors: string[]; values: Record<string, unknown> }
interface Summary { new: number; update: number; unchanged: number; ambiguous: number; error: number; total: number }
interface Section { entity: string; label: string; summary: Summary; rows: PreviewRow[] }
interface Preview { previewToken: string; entity: string; canCommit: boolean; summary: Summary; sections: Section[] }
type ImportEntity = 'workbook' | 'organizations' | 'users';
const ACTION: Record<string, string> = { new: '추가', update: '변경', unchanged: '변경 없음', error: '오류', ambiguous: '모호' };
const FIELD_LABEL: Record<string, string> = {
  externalKey: '코드', kind: '구분', name: '이름/조직명', parentExternalKey: '상위 코드', teamName: '팀', employeeNumber: '사번', userId: '사용자 ID', active: '사용',
};
const describe = (values: Record<string, unknown>) => Object.entries(values)
  .filter(([k, v]) => v !== null && v !== '' && k in FIELD_LABEL)
  .map(([k, v]) => `${FIELD_LABEL[k]}=${k === 'kind' ? (v === 'division' ? '담당 조직' : '팀') : k === 'active' ? (v ? '사용' : '비활성') : String(v)}`).join(' · ');

function ImportWizard() {
  const toast = useToast();
  const { reloadUsers } = useSession();
  const [entity, setEntity] = useState<ImportEntity>('workbook');
  const [encoding, setEncoding] = useState('utf-8');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [commitKey, setCommitKey] = useState(newKey());
  const upload = async (file: File) => {
    setBusy(true);
    try {
      const f = new FormData();
      f.set('entity', entity);
      f.set('encoding', encoding);
      f.set('file', file);
      setPreview(await api.form<Preview>('/imports/masters/preview', f));
      setCommitKey(newKey());
    } catch (e) { setPreview(null); toast('err', errText(e)); } finally { setBusy(false); }
  };
  const commit = async () => {
    if (!preview) return;
    setBusy(true);
    try {
      const r = await api.post<{ created: number; updated: number; unchanged: number }>('/imports/masters/commit', { previewToken: preview.previewToken }, { key: commitKey });
      toast('ok', `적용 완료: 추가 ${r.created}, 변경 ${r.updated}, 변경 없음 ${r.unchanged}`);
      setPreview(null);
      await reloadUsers();
    } catch (e) {
      toast('err', errText(e));
      if (e instanceof ApiException && (e.code === 'PREVIEW_STALE' || e.code === 'PREVIEW_EXPIRED')) setPreview(null);
    } finally { setBusy(false); }
  };
  return (
    <div>
      <div className="card">
        <h3>1. 양식 내려받기</h3>
        <p>조직과 사용자를 <strong>엑셀 한 파일</strong>에서 입력합니다. <strong>조직</strong> 시트에 코드와 조직명을 적은 뒤, <strong>사용자</strong> 시트의 팀 코드는 드롭박스에서 고르면 팀 이름이 옆에 자동으로 표시됩니다. 구분·사용 여부·상위 코드도 드롭박스로 고릅니다.</p>
        <a className="btn primary-link" href="/api/v1/imports/masters/template?entity=workbook&format=xlsx">조직 + 사용자 양식 받기 (xlsx)</a>
        <p className="hint">시트 이름('조직', '사용자')과 1행 머리글은 바꾸지 마세요. 사번은 텍스트 서식이라 앞자리 0이 유지됩니다.</p>
      </div>

      <div className="card">
        <h3>2. 파일 올려서 미리보기</h3>
        <p className="hint">미리보기에서 오류나 모호한 행이 하나라도 있으면 <strong>조직·사용자 전체 적용이 중단</strong>됩니다. 같은 코드는 같은 대상으로 보고 수정하며, 파일에 없는 조직·사용자는 삭제하거나 비활성화하지 않습니다.</p>
        <div className="row">
          <Field label="올리는 방식">
            <select value={entity} onChange={(e) => { setEntity(e.target.value as ImportEntity); setPreview(null); }}>
              <option value="workbook">조직 + 사용자 (한 파일, 권장)</option>
              <option value="organizations">조직만 (xlsx / csv)</option>
              <option value="users">사용자만 (xlsx / csv)</option>
            </select>
          </Field>
          {entity !== 'workbook' && <Field label="CSV 인코딩"><select value={encoding} onChange={(e) => setEncoding(e.target.value)}><option value="utf-8">UTF-8</option><option value="cp949">CP949 (한글 Excel 기본 CSV)</option></select></Field>}
          <Field label={entity === 'workbook' ? '파일 (xlsx)' : '파일 (xlsx / csv)'}>
            <input type="file" accept={entity === 'workbook' ? '.xlsx' : '.xlsx,.csv'} disabled={busy} onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ''; }} />
          </Field>
        </div>
        {entity !== 'workbook' && (
          <p className="hint">단일 양식: <a href={`/api/v1/imports/masters/template?entity=${entity}&format=xlsx`}>xlsx</a> · <a href={`/api/v1/imports/masters/template?entity=${entity}&format=csv`}>csv</a> (드롭박스는 한 파일 양식에서만 제공됩니다)</p>
        )}
      </div>

      {preview && (
        <div className="card">
          <h3>3. 미리보기 결과</h3>
          <p className={preview.canCommit ? 'ok-text' : 'field-error'}>
            총 {preview.summary.total}행 — 추가 {preview.summary.new}, 변경 {preview.summary.update}, 변경 없음 {preview.summary.unchanged}, 모호 {preview.summary.ambiguous}, 오류 {preview.summary.error}
            {preview.summary.total === 0 && ' (읽을 데이터가 없습니다. 시트에 입력했는지 확인하세요.)'}
          </p>
          <button type="button" className="primary" disabled={!preview.canCommit || busy} onClick={() => void commit()}>
            {preview.canCommit ? '이 내용으로 한 번에 적용' : '오류를 고친 뒤 파일을 다시 올려 주세요'}
          </button>
          {preview.sections.map((sec) => (
            <div key={sec.entity}>
              <h4>{sec.label} 시트 — 추가 {sec.summary.new} · 변경 {sec.summary.update} · 변경 없음 {sec.summary.unchanged}{sec.summary.error + sec.summary.ambiguous > 0 && <span className="field-error"> · 문제 {sec.summary.error + sec.summary.ambiguous}</span>}</h4>
              <table className="grid">
                <thead><tr><th>행</th><th>결과</th><th>내용</th><th>문제</th></tr></thead>
                <tbody>
                  {sec.rows.map((r) => (
                    <tr key={r.row} className={r.action === 'error' || r.action === 'ambiguous' ? 'bad' : ''}>
                      <td>{r.row}</td><td>{ACTION[r.action] ?? r.action}</td><td>{describe(r.values)}</td><td>{r.errors.join(' / ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}