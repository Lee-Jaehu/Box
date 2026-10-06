import { describe, expect, it } from 'vitest';
import { Editor } from '@tiptap/core';
import { NodeSelection } from '@tiptap/pm/state';
import { buildExtensions } from './schema';
import { leaveNodeSelection } from './selection';
import type { TiptapNode } from './document';

const make = (content: string) => new Editor({ extensions: buildExtensions(), content });
const json = (ed: Editor) => ed.getJSON() as TiptapNode;

describe('editor commands (jsdom)', () => {
  it('toggleTaskList wraps a paragraph into a task list', () => {
    const ed = make('<p>항목</p>');
    ed.commands.focus('start');
    expect(ed.chain().focus().toggleTaskList().run()).toBe(true);
    expect(json(ed).content?.[0].type).toBe('taskList');
    ed.destroy();
  });

  it('insertTable creates a header row', () => {
    const ed = make('<p>x</p>');
    ed.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run();
    const table = json(ed).content?.find((n) => n.type === 'table');
    expect(table?.content).toHaveLength(3);
    expect(table?.content?.[0].content?.[0].type).toBe('tableHeader');
    ed.destroy();
  });

  it('a selected gantt is replaced by a table unless the selection is moved first (regression)', () => {
    const insertGantt = (ed: Editor) => {
      ed.commands.insertContent({ type: 'gantt', attrs: { chartVersion: 1, viewMode: 'Day', items: [], displayRange: null } });
      let pos = -1;
      ed.state.doc.descendants((n, p) => {
        if (n.type.name === 'gantt') pos = p;
      });
      ed.commands.setNodeSelection(pos);
      expect(ed.state.selection).toBeInstanceOf(NodeSelection);
    };

    const unsafe = make('<p>x</p>');
    insertGantt(unsafe);
    unsafe.chain().focus().insertTable({ rows: 2, cols: 2 }).run();
    expect(json(unsafe).content?.map((n) => n.type)).not.toContain('gantt'); // 보호 없이는 사라진다
    unsafe.destroy();

    const safe = make('<p>x</p>');
    insertGantt(safe);
    leaveNodeSelection(safe);
    safe.chain().focus().insertTable({ rows: 2, cols: 2 }).run();
    const types = json(safe).content?.map((n) => n.type);
    expect(types).toContain('gantt');
    expect(types).toContain('table');
    safe.destroy();
  });

  it('Excel-like HTML table keeps rows, columns and cell text', () => {
    const ed = make('');
    ed.commands.setContent(
      '<table><tbody><tr><th>이름</th><th>값</th></tr><tr><td>가</td><td style="mso-number-format:0">1,000</td></tr></tbody></table>',
    );
    const rows = json(ed).content?.find((n) => n.type === 'table')?.content ?? [];
    expect(rows).toHaveLength(2);
    const texts = rows.map((r) => r.content?.map((c) => c.content?.[0].content?.[0].text));
    expect(texts).toEqual([['이름', '값'], ['가', '1,000']]);
    ed.destroy();
  });
});
