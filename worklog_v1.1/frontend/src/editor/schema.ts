// Tiptap 확장 구성(허용 node/mark 목록과 일치). React 의존이 없어 jsdom 왕복 테스트에서 그대로 사용한다.
import { Node, mergeAttributes } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import { Table, TableCell, TableHeader, TableRow } from '@tiptap/extension-table';
import TaskList from '@tiptap/extension-task-list';
import TaskItem from '@tiptap/extension-task-item';
import { LINK_SCHEMES } from './document';
import type { GanttAttrs } from '../gantt/adapter';

export const GanttBase = Node.create({
  name: 'gantt',
  group: 'block',
  atom: true,
  draggable: true,
  addAttributes() {
    return {
      chartVersion: { default: 1 },
      viewMode: { default: 'Day' },
      items: { default: [] },
      displayRange: { default: null },
    };
  },
  parseHTML() {
    return [{ tag: 'div[data-type="gantt"]' }];
  },
  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes({ 'data-type': 'gantt' }, HTMLAttributes)];
  },
});

/** 본문 이미지는 외부 URL이 아니라 task_attachments.id(attachmentUseId)만 저장한다. */
export const WorklogImage = Node.create({
  name: 'image',
  group: 'block',
  atom: true,
  draggable: true,
  addAttributes() {
    return {
      attachmentUseId: { default: null },
      width: { default: null },
    };
  },
  parseHTML() {
    return [{ tag: 'img[data-attachment-use-id]' }];
  },
  renderHTML({ HTMLAttributes }) {
    const { attachmentUseId, width, ...rest } = HTMLAttributes as Record<string, unknown>;
    return [
      'img',
      mergeAttributes(rest, {
        'data-attachment-use-id': attachmentUseId as string,
        src: `/api/v1/attachment-uses/${attachmentUseId}/content`,
        ...(width ? { width: String(width) } : {}),
      }),
    ];
  },
});

export function buildExtensions(opts: { gantt?: Node; image?: Node } = {}) {
  return [
    StarterKit.configure({
      heading: { levels: [1, 2, 3] },
      blockquote: false,
      code: false,
      codeBlock: false,
      horizontalRule: false,
      link: { openOnClick: false, protocols: LINK_SCHEMES.map((s) => s.replace(':', '')), autolink: false },
    }),
    Table.configure({ resizable: true }),
    TableRow,
    TableHeader,
    TableCell,
    TaskList,
    TaskItem.configure({ nested: true }),
    opts.image ?? WorklogImage,
    opts.gantt ?? GanttBase,
  ];
}

export type { GanttAttrs };
