import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { ApiException, api, getActor, setActor } from './api/client';
import type { AppInfo, List, User } from './api/types';

// ── 알림 ────────────────────────────────────────────────────────────────────
interface Toast { id: number; kind: 'ok' | 'err'; text: string }
const ToastCtx = createContext<(kind: Toast['kind'], text: string) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastHost({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast['kind'], text: string) => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs, { id, kind, text }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), kind === 'err' ? 8000 : 3500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => <div key={t.id} className={`toast ${t.kind}`}>{t.text}</div>)}
      </div>
    </ToastCtx.Provider>
  );
}

export const errText = (e: unknown): string => (e instanceof ApiException ? e.message : e instanceof Error ? e.message : '알 수 없는 오류');

// ── 작성자(= 사용자 설정, 로그인 아님) ─────────────────────────────────────
interface Session {
  info: AppInfo | null;
  users: User[];
  actor: User | null;
  setActorId: (id: string | null) => void;
  reloadUsers: () => Promise<void>;
  ready: boolean;
}
const SessionCtx = createContext<Session>({ info: null, users: [], actor: null, setActorId: () => {}, reloadUsers: async () => {}, ready: false });
export const useSession = () => useContext(SessionCtx);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [actorId, setId] = useState<string | null>(getActor());
  const [ready, setReady] = useState(false);
  const reloadUsers = useCallback(async () => {
    const l = await api.get<List<User>>('/users?active=true&limit=200');
    setUsers(l.items);
  }, []);
  useEffect(() => {
    void (async () => {
      try {
        setInfo(await api.get<AppInfo>('/app-info'));
        await reloadUsers();
      } finally {
        setReady(true);
      }
    })();
  }, [reloadUsers]);
  const actor = useMemo(() => users.find((u) => u.id === actorId) ?? null, [users, actorId]);
  const setActorId = useCallback((id: string | null) => { setActor(id); setId(id); }, []);
  return <SessionCtx.Provider value={{ info, users, actor, setActorId, reloadUsers, ready }}>{children}</SessionCtx.Provider>;
}

export function ActorPicker() {
  const { users, actor, setActorId } = useSession();
  const [open, setOpen] = useState(false);
  const teams = useMemo(() => [...new Set(users.map((u) => u.teamName ?? ''))].sort(), [users]);
  const [team, setTeam] = useState('');
  useEffect(() => { if (actor) setTeam(actor.teamName ?? ''); }, [actor]);
  const visible = users.filter((u) => !team || u.teamName === team);
  return (
    <div className="actor">
      <button type="button" className="actor-btn" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        {actor ? `작성자: ${actor.name}${actor.teamName ? ` · ${actor.teamName}` : ''}` : '작성자를 선택해 주세요'}
      </button>
      {open && (
        <div className="actor-pop" role="dialog" aria-label="작성자 설정">
          <p className="hint">로그인이 아닙니다. 기록에 표시되는 작성자를 고르는 자기신고 설정이며, 이 탭에서만 유지됩니다.</p>
          <label>팀
            <select value={team} onChange={(e) => setTeam(e.target.value)}>
              <option value="">전체</option>
              {teams.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label>이름
            <select value={actor?.id ?? ''} onChange={(e) => { setActorId(e.target.value || null); setOpen(false); }}>
              <option value="">선택…</option>
              {visible.map((u) => <option key={u.id} value={u.id}>{u.name}{u.employeeNumber ? ` (${u.employeeNumber})` : ''}</option>)}
            </select>
          </label>
          {actor && <button type="button" onClick={() => { setActorId(null); setOpen(false); }}>선택 해제</button>}
        </div>
      )}
    </div>
  );
}

// ── 공통 요소 ───────────────────────────────────────────────────────────────
export function Field({ label, children, error, hint }: { label: string; children: ReactNode; error?: string; hint?: string }) {
  return (
    <label className={`field${error ? ' has-error' : ''}`}>
      <span className="field-label">{label}</span>
      {children}
      {hint && <small className="hint">{hint}</small>}
      {error && <small className="field-error">{error}</small>}
    </label>
  );
}

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);
  return (
    <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`modal${wide ? ' wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <header><h3>{title}</h3><button type="button" onClick={onClose} aria-label="닫기">×</button></header>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): { data: T | null; loading: boolean; error: string | null; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    fn().then((d) => { if (alive) { setData(d); setError(null); } }).catch((e) => { if (alive) setError(errText(e)); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, loading, error, reload: () => setTick((t) => t + 1) };
}

export const STATUS_LABEL: Record<string, string> = {
  preparing: '준비', in_progress: '진행', on_hold: '보류', completed: '완료', cancelled: '취소', planned: '계획',
  open: '열림', resolved: '해결', closed: '종결',
};
export const fmtDate = (d: string | null | undefined) => d ?? '—';
export const todayLocal = (): string => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};
