// 공용(프로젝트) 간트: 마일스톤의 '현재 계획'만 수정한다. 확정 기준 일정과 실제일은 자동 변경하지 않는다.
import { useEffect, useRef } from 'react';
import Gantt from 'frappe-gantt';
import '../vendor/frappe-gantt.css';
import { fromFrappeChange, type GanttViewMode } from '../gantt/adapter';
import type { Milestone } from '../api/types';

interface Props {
  milestones: Milestone[];
  viewMode: GanttViewMode;
  onPlanChange: (m: Milestone, startDate: string, endDate: string) => void;
}

export function MilestoneGantt({ milestones, viewMode, onPlanChange }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<Gantt | null>(null);
  const latest = useRef(milestones);
  latest.current = milestones;
  const cb = useRef(onPlanChange);
  cb.current = onPlanChange;
  const scheduled = milestones.filter((m) => !m.isGeneral && m.plannedStart && m.plannedEnd);
  const key = scheduled.map((m) => `${m.id}:${m.plannedStart}:${m.plannedEnd}:${m.name}`).join('|');

  useEffect(() => {
    if (!host.current) return;
    if (scheduled.length === 0) { host.current.innerHTML = ''; chart.current = null; return; }
    const tasks = scheduled.map((m) => ({ id: m.id, name: m.name, start: m.plannedStart!, end: m.plannedEnd!, progress: 0 }));
    if (!chart.current) {
      host.current.innerHTML = '<svg></svg>';
      chart.current = new Gantt(host.current.querySelector('svg')!, tasks, {
        view_mode: viewMode, language: 'ko', popup: false, readonly_progress: true, scroll_to: 'start', today_button: false,
        on_date_change: (task: { id: string }, start: Date, end: Date) => {
          const m = latest.current.find((x) => x.id === task.id);
          if (!m) return;
          const { startDate, endDate } = fromFrappeChange(start, end);
          cb.current(m, startDate, endDate);
        },
      });
    } else {
      chart.current.refresh(tasks);
      chart.current.change_view_mode(viewMode, true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, viewMode]);

  const unscheduled = milestones.filter((m) => !m.isGeneral && !(m.plannedStart && m.plannedEnd));
  return (
    <div>
      <div ref={host} className="gantt-host" />
      {scheduled.length === 0 && <p className="hint">계획 일정이 있는 마일스톤이 없습니다. 아래 표에서 계획 시작/종료일을 입력하면 간트에 표시됩니다.</p>}
      {unscheduled.length > 0 && <p className="hint">일정 미정: {unscheduled.map((m) => m.name).join(', ')}</p>}
    </div>
  );
}
