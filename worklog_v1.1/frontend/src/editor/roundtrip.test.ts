import { describe, expect, it } from 'vitest';
import { Editor } from '@tiptap/core';
import { buildExtensions } from './schema';
import {
  collectImageUseIds,
  missingImageDescriptions,
  titlePreview,
  validateDocument,
  wrapDocument,
  type TiptapNode,
} from './document';

const sample: TiptapNode = {
  type: 'doc',
  content: [
    { type: 'heading', attrs: { level: 2 }, content: [{ type: 'text', text: '한글 제목' }] },
    {
      type: 'paragraph',
      content: [
        { type: 'text', text: '굵게', marks: [{ type: 'bold' }] },
        { type: 'text', text: ' 링크', marks: [{ type: 'link', attrs: { href: 'https://example.com' } }] },
      ],
    },
    {
      type: 'taskList',
      content: [
        { type: 'taskItem', attrs: { checked: true }, content: [{ type: 'paragraph', content: [{ type: 'text', text: '완료 항목' }] }] },
        { type: 'taskItem', attrs: { checked: false }, content: [{ type: 'paragraph', content: [{ type: 'text', text: '대기 항목' }] }] },
      ],
    },
    {
      type: 'table',
      content: [
        {
          type: 'tableRow',
          content: [
            { type: 'tableHeader', attrs: { colspan: 2, rowspan: 1 }, content: [{ type: 'paragraph', content: [{ type: 'text', text: '병합 헤더' }] }] },
          ],
        },
        {
          type: 'tableRow',
          content: [
            { type: 'tableCell', attrs: { colspan: 1, rowspan: 2 }, content: [{ type: 'paragraph', content: [{ type: 'text', text: 'A' }] }, { type: 'paragraph', content: [{ type: 'text', text: '둘째 줄' }] }] },
            { type: 'tableCell', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'B' }] }] },
          ],
        },
        {
          type: 'tableRow',
          content: [{ type: 'tableCell', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'C' }] }] }],
        },
      ],
    },
    {
      type: 'gantt',
      attrs: {
        chartVersion: 1,
        viewMode: 'Week',
        items: [
          { itemId: 'g1', label: '설계', startDate: '2026-10-04', endDate: '2026-10-06', progressPercent: 30 },
          { itemId: 'g2', label: '하루짜리', startDate: '2026-10-07', endDate: '2026-10-07' },
        ],
        displayRange: { start: '2026-10-01', end: '2026-10-31' },
      },
    },
    { type: 'image', attrs: { attachmentUseId: 'use-1', width: 320 } },
  ],
};

function roundTrip(json: TiptapNode): TiptapNode {
  const ed = new Editor({ extensions: buildExtensions(), content: json });
  const out = ed.getJSON() as TiptapNode;
  ed.destroy();
  return out;
}

/** 필수 보존 정보만 비교하기 위해 Tiptap이 채우는 기본 attrs(null 값 등)를 제거 */
function strip(n: TiptapNode): unknown {
  const attrs = Object.fromEntries(Object.entries(n.attrs ?? {}).filter(([, v]) => v !== null && v !== undefined));
  if (n.type === 'tableCell' || n.type === 'tableHeader') {
    const a = attrs as Record<string, unknown>;
    delete a.colwidth;
    if (a.colspan === 1) delete a.colspan; // Tiptap이 채우는 기본값
    if (a.rowspan === 1) delete a.rowspan;
  }
  return {
    type: n.type,
    ...(Object.keys(attrs).length ? { attrs } : {}),
    ...(n.text ? { text: n.text } : {}),
    ...(n.marks ? { marks: n.marks.map((m) => ({ type: m.type, ...(m.attrs?.href ? { href: m.attrs.href } : {}) })) } : {}),
    ...(n.content ? { content: n.content.map(strip) } : {}),
  };
}

describe('document JSON roundtrip (Tiptap 3.31.4, jsdom)', () => {
  it('preserves text, marks, task list checks, table spans, gantt payload, image use id', () => {
    const out = roundTrip(sample);
    const find = (n: TiptapNode, type: string): TiptapNode[] =>
      [n.type === type ? n : null, ...(n.content ?? []).flatMap((c) => find(c, type))].filter(Boolean) as TiptapNode[];

    const gantt = find(out, 'gantt')[0];
    expect(gantt.attrs?.items).toEqual((sample.content![4].attrs as { items: unknown }).items);
    expect(gantt.attrs?.viewMode).toBe('Week');
    expect(gantt.attrs?.displayRange).toEqual({ start: '2026-10-01', end: '2026-10-31' });

    const image = find(out, 'image')[0];
    expect(image.attrs?.attachmentUseId).toBe('use-1');
    expect(image.attrs?.width).toBe(320);

    const checks = find(out, 'taskItem').map((t) => t.attrs?.checked);
    expect(checks).toEqual([true, false]);

    const header = find(out, 'tableHeader')[0];
    expect(header.attrs?.colspan).toBe(2);
    const spanned = find(out, 'tableCell')[0];
    expect(spanned.attrs?.rowspan).toBe(2);
    expect(find(spanned, 'paragraph')).toHaveLength(2);

    // 전체 구조가 두 번째 왕복에서도 변하지 않는다(idempotent).
    expect(strip(roundTrip(out))).toEqual(strip(out));
    // 내용(텍스트/구조)이 원본과 같다.
    expect(strip(out)).toEqual(strip(sample));
  });

  it('saved document passes the contract validator', () => {
    const issues = validateDocument(wrapDocument(roundTrip(sample)));
    expect(issues).toEqual([]);
  });

  it('unknown node and unsafe link are reported with a path, not silently dropped', () => {
    const bad: TiptapNode = {
      type: 'doc',
      content: [
        { type: 'codeBlock', content: [{ type: 'text', text: 'x' }] },
        { type: 'paragraph', content: [{ type: 'text', text: 'l', marks: [{ type: 'link', attrs: { href: 'javascript:alert(1)' } }] }] },
      ],
    };
    const codes = validateDocument(wrapDocument(bad)).map((i) => `${i.code}@${i.path}`);
    expect(codes).toContain('UNKNOWN_NODE@doc.content[0]');
    expect(codes.some((c) => c.startsWith('UNSAFE_LINK'))).toBe(true);
  });

  it('image requires a description for every use in the body', () => {
    expect(collectImageUseIds(sample)).toEqual(['use-1']);
    expect(missingImageDescriptions(sample, {})).toEqual(['use-1']);
    expect(missingImageDescriptions(sample, { 'use-1': '  ' })).toEqual(['use-1']);
    expect(missingImageDescriptions(sample, { 'use-1': '설명' })).toEqual([]);
  });

  it('gantt item with end before start is a validation issue', () => {
    const doc: TiptapNode = {
      type: 'doc',
      content: [{ type: 'gantt', attrs: { chartVersion: 1, viewMode: 'Day', items: [{ itemId: 'x', label: 'a', startDate: '2026-10-05', endDate: '2026-10-01' }], displayRange: null } }],
    };
    expect(validateDocument(wrapDocument(doc)).map((i) => i.code)).toContain('INVALID_GANTT_ITEM');
  });

  it('titlePreview uses the first text', () => {
    expect(titlePreview(sample)).toBe('한글 제목 굵게 링크 완료 항목 대기 항목 병합 헤더 A 둘째 줄 B C'.slice(0, 60));
  });
});
