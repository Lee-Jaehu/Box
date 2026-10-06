// 달력 날짜 계산(로컬 달력 날짜 문자열 YYYY-MM-DD만 사용 — UTC 변환 금지)
import { addDays, formatLocalDate } from '../gantt/adapter';

/** 해당 월을 일요일 시작 6주(42칸)로 반환. inMonth=false 는 앞뒤 달 날짜 */
export function monthGrid(year: number, month: number): { date: string; inMonth: boolean }[] {
  const first = new Date(year, month - 1, 1);
  const start = addDays(formatLocalDate(first), -first.getDay());
  return Array.from({ length: 42 }, (_, i) => {
    const date = addDays(start, i);
    return { date, inMonth: Number(date.slice(5, 7)) === month };
  });
}

export function monthRange(year: number, month: number): { from: string; to: string } {
  const g = monthGrid(year, month);
  return { from: g[0].date, to: g[41].date }; // 앞뒤 달 날짜의 건수도 표시하기 위해 보이는 전체 범위
}

export function shiftMonth(year: number, month: number, delta: number): { year: number; month: number } {
  const d = new Date(year, month - 1 + delta, 1);
  return { year: d.getFullYear(), month: d.getMonth() + 1 };
}
