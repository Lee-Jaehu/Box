import { describe, expect, it } from 'vitest';
import { addDays, fromFrappeChange, isIsoDate, toFrappeTasks, validateItem } from './adapter';

describe('gantt adapter', () => {
  it('isIsoDate rejects impossible dates', () => {
    expect(isIsoDate('2026-02-30')).toBe(false);
    expect(isIsoDate('2026-10-04')).toBe(true);
    expect(isIsoDate('2026-1-4')).toBe(false);
  });

  it('end date stays inclusive when Frappe reports end-1s', () => {
    // Frappe가 3일짜리 막대(10/4~10/6)를 이동했을 때 end 콜백은 10/6 23:59:59
    const start = new Date(2026, 9, 4);
    const end = new Date(2026, 9, 6, 23, 59, 59);
    expect(fromFrappeChange(start, end)).toEqual({ startDate: '2026-10-04', endDate: '2026-10-06' });
  });

  it('one-day bar keeps same start/end', () => {
    const start = new Date(2026, 9, 4);
    const end = new Date(2026, 9, 4, 23, 59, 59);
    expect(fromFrappeChange(start, end)).toEqual({ startDate: '2026-10-04', endDate: '2026-10-04' });
  });

  it('does not shift across month boundary or timezone', () => {
    expect(addDays('2026-10-31', 1)).toBe('2026-11-01');
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28');
  });

  it('maps items to frappe tasks without changing dates', () => {
    const t = toFrappeTasks([{ itemId: 'a', label: '한글', startDate: '2026-10-04', endDate: '2026-10-06' }]);
    expect(t[0]).toMatchObject({ id: 'a', name: '한글', start: '2026-10-04', end: '2026-10-06' });
  });

  it('validates end >= start and label', () => {
    expect(validateItem({ itemId: 'a', label: 'x', startDate: '2026-10-05', endDate: '2026-10-04' })).toMatch('종료일');
    expect(validateItem({ itemId: 'a', label: ' ', startDate: '2026-10-05', endDate: '2026-10-05' })).toMatch('이름');
    expect(validateItem({ itemId: 'a', label: 'x', startDate: '2026-10-05', endDate: '2026-10-05' })).toBeNull();
  });
});
