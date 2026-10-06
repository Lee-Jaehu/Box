// 보고자료 기간 계산 (로컬 달력 날짜 문자열만 사용 — UTC 변환 금지). 서버(weekly_report)와 같은 ISO 주차(월~일) 규칙.
import { addDays, parseLocalDate } from '../gantt/adapter';

const WEEKDAY = ['일', '월', '화', '수', '목', '금', '토'];

/** 날짜가 속한 ISO 주차: { week: '2026-W40', start: 월요일, end: 일요일 } */
export function isoWeekOf(date: string): { week: string; start: string; end: string } {
  const d = parseLocalDate(date);
  const dow = (d.getDay() + 6) % 7; // 월=0 … 일=6
  const start = addDays(date, -dow);
  const thursday = parseLocalDate(addDays(start, 3)); // ISO 주차의 연도 = 그 주 목요일의 연도
  const year = thursday.getFullYear();
  const jan4 = new Date(year, 0, 4);
  const week1Monday = new Date(year, 0, 4 - ((jan4.getDay() + 6) % 7));
  const week = Math.round((parseLocalDate(start).getTime() - week1Monday.getTime()) / (7 * 86400000)) + 1;
  return { week: `${year}-W${String(week).padStart(2, '0')}`, start, end: addDays(start, 6) };
}

export function shortDay(date: string): string {
  const d = parseLocalDate(date);
  return `${d.getMonth() + 1}/${d.getDate()}(${WEEKDAY[d.getDay()]})`;
}

export function weekLabel(date: string): string {
  const w = isoWeekOf(date);
  return `${w.week} · ${shortDay(w.start)} ~ ${shortDay(w.end)}`;
}

/** 월간 종합이 다루는 ISO 주차: 목요일이 그 달에 있는 주 (서버 month_weeks 와 같음) */
export function monthWeeks(month: string): { weeks: string[]; start: string; end: string } {
  const [y, m] = month.split('-').map(Number);
  let day = `${y}-${String(m).padStart(2, '0')}-01`;
  const first = parseLocalDate(day);
  day = addDays(day, (4 - first.getDay() + 7) % 7); // 첫 목요일
  const weeks: string[] = [];
  let start = '';
  let end = '';
  while (Number(day.slice(5, 7)) === m) {
    const w = isoWeekOf(day);
    if (!start) start = w.start;
    end = w.end;
    weeks.push(w.week);
    day = addDays(day, 7);
  }
  return { weeks, start, end };
}

export function daysBetween(from: string, to: string): number {
  return Math.round((parseLocalDate(to).getTime() - parseLocalDate(from).getTime()) / 86400000) + 1;
}
