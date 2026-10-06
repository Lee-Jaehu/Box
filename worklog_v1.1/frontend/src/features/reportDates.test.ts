import { describe, expect, it } from 'vitest';
import { daysBetween, isoWeekOf, monthWeeks, weekLabel } from './reportDates';

describe('reportDates', () => {
  it('ISO 주차는 월~일이고 연말·연초 경계를 서버와 같게 계산한다', () => {
    expect(isoWeekOf('2026-10-04')).toEqual({ week: '2026-W40', start: '2026-09-28', end: '2026-10-04' }); // 일요일
    expect(isoWeekOf('2026-10-05').week).toBe('2026-W41'); // 월요일부터 다음 주
    expect(isoWeekOf('2027-01-01').week).toBe('2026-W53'); // 2026년은 53주
    expect(isoWeekOf('2025-12-29').week).toBe('2026-W01');
    expect(weekLabel('2026-10-01')).toBe('2026-W40 · 9/28(월) ~ 10/4(일)');
  });

  it('월간 종합 주차는 목요일이 그 달에 있는 주', () => {
    expect(monthWeeks('2026-10')).toEqual({ weeks: ['2026-W40', '2026-W41', '2026-W42', '2026-W43', '2026-W44'], start: '2026-09-28', end: '2026-11-01' });
    expect(monthWeeks('2026-09').weeks).toEqual(['2026-W36', '2026-W37', '2026-W38', '2026-W39']);
    expect(daysBetween('2026-10-01', '2026-10-01')).toBe(1);
  });
});
