import { useEffect, useRef } from 'react';
import { NodeViewWrapper, ReactNodeViewRenderer, type NodeViewProps } from '@tiptap/react';
import Gantt from 'frappe-gantt';
// frappe-gantt 1.2.2의 package exports가 CSS 서브패스를 열어두지 않아 dist CSS를 vendor로 복사해 사용한다(MIT, 고지는 THIRD_PARTY_NOTICES).
import '../vendor/frappe-gantt.css';
import {
  fromFrappeChange,
  todayLocal,
  toFrappeTasks,
  validateItem,
  type GanttAttrs,
  type GanttItem,
  type GanttViewMode,
} from '../gantt/adapter';
import { GanttBase } from './schema';
import { createId } from "../utils/id";

function GanttNodeView({ node, updateAttributes, deleteNode, editor }: NodeViewProps) {
  const attrs = node.attrs as GanttAttrs;
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<Gantt | null>(null);
  const editable = editor.isEditable;
  const itemsRef = useRef(attrs.items);
  itemsRef.current = attrs.items;

  useEffect(() => {
    if (!host.current || attrs.items.length === 0) return;
    const tasks = toFrappeTasks(attrs.items);
    if (!chart.current) {
      host.current.innerHTML = '<svg></svg>';
      chart.current = new Gantt(host.current.querySelector('svg')!, tasks, {
        view_mode: attrs.viewMode,
        language: 'ko',
        popup: false,
        readonly_progress: true,
        readonly: !editable,
        scroll_to: 'start',
        today_button: false,
        on_date_change: (task: { id: string }, start: Date, end: Date) => {
          const { startDate, endDate } = fromFrappeChange(start, end);
          updateAttributes({
            items: itemsRef.current.map((it) => (it.itemId === task.id ? { ...it, startDate, endDate } : it)),
          });
        },
      });
    } else {
      chart.current.refresh(tasks);
      chart.current.change_view_mode(attrs.viewMode, true);
    }
  }, [attrs.items, attrs.viewMode, editable, updateAttributes]);

  const patchItem = (id: string, patch: Partial<GanttItem>) =>
    updateAttributes({ items: attrs.items.map((it) => (it.itemId === id ? { ...it, ...patch } : it)) });

  const addItem = () => {
    const last = attrs.items[attrs.items.length - 1];
    const start = last?.endDate ?? todayLocal();
    updateAttributes({
      items: [...attrs.items, { itemId: createId(), label: '새 작업', startDate: start, endDate: start }],
    });
  };

  return (
    <NodeViewWrapper className="gantt-node" data-type="gantt">
      <div className="gantt-head">
        <strong>간트</strong>
        <select
          value={attrs.viewMode}
          disabled={!editable}
          onChange={(e) => updateAttributes({ viewMode: e.target.value as GanttViewMode })}
        >
          <option value="Day">일</option>
          <option value="Week">주</option>
          <option value="Month">월</option>
        </select>
        {editable && <button type="button" onClick={addItem}>+ 작업 추가</button>}
        {editable && <button type="button" onClick={() => deleteNode()}>간트 삭제</button>}
      </div>
      <div ref={host} className="gantt-host" />
      <table className="gantt-items">
        <tbody>
          {attrs.items.map((it) => {
            const err = validateItem(it);
            return (
              <tr key={it.itemId} className={err ? 'invalid' : ''}>
                <td>
                  <input aria-label="작업 이름" value={it.label} disabled={!editable}
                    onChange={(e) => patchItem(it.itemId, { label: e.target.value })} />
                </td>
                <td>
                  <input type="date" aria-label="시작일" value={it.startDate} disabled={!editable}
                    onChange={(e) => patchItem(it.itemId, { startDate: e.target.value })} />
                </td>
                <td>
                  <input type="date" aria-label="종료일" value={it.endDate} disabled={!editable}
                    onChange={(e) => patchItem(it.itemId, { endDate: e.target.value })} />
                </td>
                <td>
                  {editable && (
                    <button type="button" onClick={() => updateAttributes({ items: attrs.items.filter((x) => x.itemId !== it.itemId) })}>삭제</button>
                  )}
                  {err && <span className="field-error">{err}</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </NodeViewWrapper>
  );
}

export const GanttNode = GanttBase.extend({
  addNodeView() {
    return ReactNodeViewRenderer(GanttNodeView);
  },
});
