// 얇은 API 클라이언트. 변경 요청에는 Idempotency-Key 와 X-Actor-Id(선택 작성자, 인증 아님)를 붙인다.
export interface FieldError {
  field: string;
  code: string;
  message: string;
}

import { createId } from "../utils/id";

export class ApiException extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public fieldErrors: FieldError[] = [],
    public currentRevision?: number,
    public resourceId?: string,
    public retryable = false,
  ) {
    super(message);
  }
}

const ACTOR_KEY = 'worklog.actorId';
let actorId: string | null = null;
try {
  actorId = sessionStorage.getItem(ACTOR_KEY);
} catch {
  actorId = null;
}

export function getActor(): string | null {
  return actorId;
}

export function setActor(id: string | null): void {
  actorId = id;
  try {
    if (id) sessionStorage.setItem(ACTOR_KEY, id);
    else sessionStorage.removeItem(ACTOR_KEY);
  } catch {
    /* 저장소를 못 써도 현재 탭 메모리 값으로 동작 */
  }
}

export const newKey = (): string => createId();

interface Options {
  key?: string;
  actor?: boolean;
}

async function parse(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

async function request<T>(method: string, path: string, body?: unknown, opts: Options = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined && !(body instanceof FormData)) headers['Content-Type'] = 'application/json';
  if (actorId && opts.actor !== false) headers['X-Actor-Id'] = actorId;
  if (method !== 'GET') headers['Idempotency-Key'] = opts.key ?? newKey();
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
    });
  } catch {
    throw new ApiException(0, 'NETWORK', '서버에 연결할 수 없습니다. 입력한 내용은 브라우저에 임시저장되어 있습니다.', [], undefined, undefined, true);
  }
  const json = (await parse(res)) as { data?: T; error?: { code: string; message: string; fieldErrors?: FieldError[]; currentRevision?: number; resourceId?: string; retryable?: boolean } } | null;
  if (!res.ok) {
    const e = json?.error;
    throw new ApiException(res.status, e?.code ?? 'ERROR', e?.message ?? `요청에 실패했습니다 (${res.status})`, e?.fieldErrors ?? [], e?.currentRevision, e?.resourceId, e?.retryable ?? res.status === 503);
  }
  return (json?.data ?? null) as T;
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown, opts?: Options) => request<T>('POST', path, body ?? {}, opts),
  put: <T>(path: string, body: unknown, opts?: Options) => request<T>('PUT', path, body, opts),
  patch: <T>(path: string, body: unknown, opts?: Options) => request<T>('PATCH', path, body, opts),
  del: <T>(path: string, opts?: Options) => request<T>('DELETE', path, undefined, opts),
  form: <T>(path: string, form: FormData, opts?: Options) => request<T>('POST', path, form, opts),
};

export const qs = (params: Record<string, string | number | boolean | null | undefined>): string => {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') u.set(k, String(v));
  const s = u.toString();
  return s ? `?${s}` : '';
};
