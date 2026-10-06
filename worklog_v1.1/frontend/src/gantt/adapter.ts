// 간트 어댑터: 저장 계약(YYYY-MM-DD, 종료일 포함)과 Frappe Gantt(Date, 종료 배타)의 경계.
// Frappe Gantt 1.2.2 관찰 결과:
//  - 입력 end가 자정이면 내부에서 +24h 하여 "종료일 포함"으로 그린다.
//  - on_date_change 콜백의 end는 (내부 배타 종료 - 1초)이므로 로컬 날짜로 포맷하면 포함 종료일이 된다.
// 따라서 저장 형식은 포함 종료일 하나로 통일하고, 타임존은 로컬 달력 날짜만 사용한다(UTC 변환 금지).
import { createId } from "../utils/id";
export type GanttViewMode = 'Day' | 'Week' | 'Month';

export interface GanttItem {
  itemId: string;
  label: string;
  startDate: string; // YYYY-MM-DD
  endDate: string; // YYYY-MM-DD, inclusive
  progressPercent?: number;
}

export interface GanttAttrs {
  chartVersion: number;
  viewMode: GanttViewMode;
  items: GanttItem[];
  displayRange?: { start: string; end: string } | null;
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export function isIsoDate(value: unknown): value is string {
  if (typeof value !== 'string' || !DATE_RE.test(value)) return false;
  const [y, m, d] = value.split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  return dt.getFullYear() === y && dt.getMonth() === m - 1 && dt.getDate() === d;
}

export function formatLocalDate(d: Date): string {
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

/** 브라우저 로컬(사용자 PC, Asia/Seoul 가정) 달력 날짜. toISOString()은 UTC라서 자정 전후에 하루가 어긋난다. */
export function todayLocal(): string {
  return formatLocalDate(new Date());
}

export function parseLocalDate(value: string): Date {
  const [y, m, d] = value.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function addDays(value: string, days: number): string {
  const d = parseLocalDate(value);
  d.setDate(d.getDate() + days);
  return formatLocalDate(d);
}

export interface FrappeTask {
  id: string;
  name: string;
  start: string;
  end: string;
  progress: number;
}

export function toFrappeTasks(items: GanttItem[]): FrappeTask[] {
  return items.map((it) => ({
    id: it.itemId,
    name: it.label,
    start: it.startDate,
    end: it.endDate, // 자정 end는 Frappe가 포함 종료로 처리
    progress: it.progressPercent ?? 0,
  }));
}

/** Frappe on_date_change(task, start, end) -> 포함 종료일 기준 날짜 쌍 */
export function fromFrappeChange(start: Date, end: Date): { startDate: string; endDate: string } {
  const startDate = formatLocalDate(start);
  let endDate = formatLocalDate(end);
  if (endDate < startDate) endDate = startDate; // 하루짜리 막대 보호
  return { startDate, endDate };
}

export function validateItem(item: Partial<GanttItem>): string | null {
  if (!item.itemId) return 'itemId가 필요합니다.';
  if (!item.label || !item.label.trim()) return '작업 이름이 필요합니다.';
  if (!isIsoDate(item.startDate)) return '시작일 형식이 올바르지 않습니다.';
  if (!isIsoDate(item.endDate)) return '종료일 형식이 올바르지 않습니다.';
  if (item.endDate < item.startDate) return '종료일은 시작일보다 빠를 수 없습니다.';
  if (item.progressPercent !== undefined && (item.progressPercent < 0 || item.progressPercent > 100)) {
    return '진행률은 0~100이어야 합니다.';
  }
  return null;
}

export function updateItem(attrs: GanttAttrs, itemId: string, patch: Partial<GanttItem>): GanttAttrs {
  return { ...attrs, items: attrs.items.map((it) => (it.itemId === itemId ? { ...it, ...patch } : it)) };
}

export function defaultGanttAttrs(today: string): GanttAttrs {
  return {
    chartVersion: 1,
    viewMode: 'Day',
    items: [
      { itemId: createId(), label: '새 작업', startDate: today, endDate: addDays(today, 2) },
    ],
    displayRange: null,
  };
}
