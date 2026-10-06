// 본문 문서 계약: {documentVersion, format, doc}. 알 수 없는 node는 조용히 삭제하지 않고 위치와 함께 오류 처리.
import { isIsoDate, validateItem } from '../gantt/adapter';

export const DOCUMENT_VERSION = 1;
export const DOCUMENT_FORMAT = 'tiptap-json';

export const ALLOWED_NODES = new Set([
  'doc', 'paragraph', 'text', 'heading', 'bulletList', 'orderedList', 'listItem',
  'taskList', 'taskItem', 'table', 'tableRow', 'tableHeader', 'tableCell',
  'image', 'gantt', 'hardBreak',
]);
export const ALLOWED_MARKS = new Set(['bold', 'italic', 'underline', 'strike', 'link']);
export const LINK_SCHEMES = ['http:', 'https:', 'mailto:'];

export interface TiptapNode {
  type: string;
  attrs?: Record<string, unknown>;
  content?: TiptapNode[];
  marks?: { type: string; attrs?: Record<string, unknown> }[];
  text?: string;
}

export interface WorklogDocument {
  documentVersion: number;
  format: string;
  doc: TiptapNode;
}

export interface DocIssue {
  path: string;
  code: string;
  message: string;
}

export const emptyDocument = (): WorklogDocument => ({
  documentVersion: DOCUMENT_VERSION,
  format: DOCUMENT_FORMAT,
  doc: { type: 'doc', content: [{ type: 'paragraph' }] },
});

export const wrapDocument = (doc: TiptapNode): WorklogDocument => ({
  documentVersion: DOCUMENT_VERSION,
  format: DOCUMENT_FORMAT,
  doc,
});

function isSafeLink(href: unknown): boolean {
  if (typeof href !== 'string') return false;
  try {
    return LINK_SCHEMES.includes(new URL(href).protocol);
  } catch {
    return false;
  }
}

export function validateDocument(document: WorklogDocument): DocIssue[] {
  const issues: DocIssue[] = [];
  if (document.documentVersion !== DOCUMENT_VERSION) {
    issues.push({ path: 'documentVersion', code: 'UNSUPPORTED_VERSION', message: '지원하지 않는 문서 버전입니다.' });
  }
  if (document.format !== DOCUMENT_FORMAT) {
    issues.push({ path: 'format', code: 'UNSUPPORTED_FORMAT', message: '지원하지 않는 문서 형식입니다.' });
  }
  const walk = (node: TiptapNode, path: string) => {
    if (!ALLOWED_NODES.has(node.type)) {
      issues.push({ path, code: 'UNKNOWN_NODE', message: `알 수 없는 node: ${node.type}` });
      return;
    }
    for (const mark of node.marks ?? []) {
      if (!ALLOWED_MARKS.has(mark.type)) {
        issues.push({ path, code: 'UNKNOWN_MARK', message: `알 수 없는 mark: ${mark.type}` });
      } else if (mark.type === 'link' && !isSafeLink(mark.attrs?.href)) {
        issues.push({ path, code: 'UNSAFE_LINK', message: '허용되지 않는 링크 주소입니다.' });
      }
    }
    if (node.type === 'image' && !node.attrs?.attachmentUseId) {
      issues.push({ path, code: 'IMAGE_WITHOUT_ATTACHMENT', message: '이미지는 첨부 사용처 ID가 필요합니다.' });
    }
    if (node.type === 'gantt') {
      const items = (node.attrs?.items as { itemId?: string }[] | undefined) ?? [];
      const seen = new Set<string>();
      items.forEach((item, i) => {
        const err = validateItem(item as never);
        if (err) issues.push({ path: `${path}.attrs.items[${i}]`, code: 'INVALID_GANTT_ITEM', message: err });
        if (item.itemId) {
          if (seen.has(item.itemId)) {
            issues.push({ path: `${path}.attrs.items[${i}]`, code: 'DUPLICATE_GANTT_ITEM', message: 'itemId가 중복됩니다.' });
          }
          seen.add(item.itemId);
        }
      });
      const range = node.attrs?.displayRange as { start?: string; end?: string } | null | undefined;
      if (range && (!isIsoDate(range.start) || !isIsoDate(range.end))) {
        issues.push({ path: `${path}.attrs.displayRange`, code: 'INVALID_GANTT_RANGE', message: '표시 범위 날짜가 올바르지 않습니다.' });
      }
    }
    (node.content ?? []).forEach((child, i) => walk(child, `${path}.content[${i}]`));
  };
  walk(document.doc, 'doc');
  return issues;
}

/** 문서에서 image node의 attachmentUseId를 순서대로 수집 (사용처 일치·설명 검증에 사용) */
export function collectImageUseIds(node: TiptapNode, out: string[] = []): string[] {
  if (node.type === 'image' && typeof node.attrs?.attachmentUseId === 'string') {
    out.push(node.attrs.attachmentUseId);
  }
  (node.content ?? []).forEach((c) => collectImageUseIds(c, out));
  return out;
}

/** 이미지 설명 필수: 본문에 쓰인 모든 사용처는 비어있지 않은 설명이 있어야 한다. */
export function missingImageDescriptions(
  node: TiptapNode,
  descriptions: Record<string, string | undefined>,
): string[] {
  return collectImageUseIds(node).filter((id) => !descriptions[id]?.trim());
}

/** 첫 텍스트 기반 접힌 카드 요약 */
export function titlePreview(node: TiptapNode, max = 60): string {
  const parts: string[] = [];
  const walk = (n: TiptapNode) => {
    if (parts.join(' ').length >= max) return;
    if (n.type === 'text' && n.text) parts.push(n.text);
    (n.content ?? []).forEach(walk);
  };
  walk(node);
  const text = parts.join(' ').replace(/\s+/g, ' ').trim();
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

export function hasContent(node: TiptapNode): boolean {
  if (node.type === 'text') return !!node.text?.trim();
  if (['image', 'gantt', 'table'].includes(node.type)) return true;
  return (node.content ?? []).some(hasContent);
}
