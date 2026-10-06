import { describe, expect, it } from 'vitest';
import { monthGrid, monthRange, shiftMonth } from './calendar';

describe('calendar', () => {
  it('2026-10 starts on Thursday: grid begins on Sunday 2026-09-27 and has 42 cells', () => {
    const g = monthGrid(2026, 10);
    expect(g).toHaveLength(42);
    expect(g[0]).toEqual({ date: '2026-09-27', inMonth: false });
    expect(g[4]).toEqual({ date: '2026-10-01', inMonth: true });
    expect(g.filter((c) => c.inMonth)).toHaveLength(31);
    expect(g[41].date).toBe('2026-11-07');
  });
  it('a month starting on Sunday has no leading days', () => {
    expect(monthGrid(2026, 2)[0]).toEqual({ date: '2026-02-01', inMonth: true });
  });
  it('range covers the visible grid and month shifting crosses years', () => {
    expect(monthRange(2026, 10)).toEqual({ from: '2026-09-27', to: '2026-11-07' });
    expect(shiftMonth(2026, 12, 1)).toEqual({ year: 2027, month: 1 });
    expect(shiftMonth(2026, 1, -1)).toEqual({ year: 2025, month: 12 });
  });
});
