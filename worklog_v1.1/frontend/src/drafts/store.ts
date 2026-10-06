// 초안 저장소. 운영은 IndexedDB, 테스트는 메모리 구현을 주입한다.
import type { LogDraft } from './logDraft';

export interface DraftRecord {
  key: string;
  draft: LogDraft;
  updatedAt: string;
}

export interface DraftStore {
  get(key: string): Promise<DraftRecord | null>;
  put(record: DraftRecord): Promise<void>;
  delete(key: string): Promise<void>;
  listPrefix(prefix: string): Promise<DraftRecord[]>;
}

export class MemoryDraftStore implements DraftStore {
  private m = new Map<string, DraftRecord>();
  async get(key: string) { return this.m.get(key) ?? null; }
  async put(r: DraftRecord) { this.m.set(r.key, structuredClone(r)); }
  async delete(key: string) { this.m.delete(key); }
  async listPrefix(prefix: string) { return [...this.m.values()].filter((r) => r.key.startsWith(prefix)); }
}

const DB_NAME = 'worklog-drafts';
const STORE = 'drafts';

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => { req.result.createObjectStore(STORE, { keyPath: 'key' }); };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function tx<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return open().then((db) => new Promise<T>((resolve, reject) => {
    const t = db.transaction(STORE, mode);
    const r = fn(t.objectStore(STORE));
    t.oncomplete = () => { db.close(); resolve(r.result); };
    t.onerror = () => { db.close(); reject(t.error); };
    t.onabort = () => { db.close(); reject(t.error); };
  }));
}

/** IndexedDB 를 쓸 수 없는 환경(사생활 보호 모드 등)에서는 메모리로 대체하고 사용자에게 알린다. */
export class IdbDraftStore implements DraftStore {
  available = typeof indexedDB !== 'undefined';
  private fallback = new MemoryDraftStore();
  private failed = false;
  get degraded() { return !this.available || this.failed; }

  private async guard<T>(fn: () => Promise<T>, alt: () => Promise<T>): Promise<T> {
    if (!this.available) return alt();
    try { return await fn(); } catch { this.failed = true; return alt(); }
  }
  get(key: string) { return this.guard(async () => ((await tx('readonly', (s) => s.get(key))) as DraftRecord | undefined) ?? null, () => this.fallback.get(key)); }
  put(r: DraftRecord) { return this.guard(async () => { await tx('readwrite', (s) => s.put(r)); }, () => this.fallback.put(r)); }
  delete(key: string) { return this.guard(async () => { await tx('readwrite', (s) => s.delete(key)); }, () => this.fallback.delete(key)); }
  listPrefix(prefix: string) {
    return this.guard(async () => ((await tx('readonly', (s) => s.getAll())) as DraftRecord[]).filter((r) => r.key.startsWith(prefix)), () => this.fallback.listPrefix(prefix));
  }
}

export const draftStore = new IdbDraftStore();
