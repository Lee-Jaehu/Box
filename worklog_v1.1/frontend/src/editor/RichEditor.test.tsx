// 회귀: 저장 후 목록이 다시 로드되며 docKey/value 가 함께 바뀔 때(에디터 인스턴스 교체) 앱 전체가 죽던 문제.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { RichEditor } from './RichEditor';
import { wrapDocument, type WorklogDocument } from './document';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const doc = (text: string): WorklogDocument => wrapDocument({ type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] });
const empty = (): WorklogDocument => wrapDocument({ type: 'doc', content: [{ type: 'paragraph' }] });

let host: HTMLDivElement;
let root: Root;
const errors: unknown[] = [];
const onWindowError = (e: ErrorEvent) => { errors.push(e.error ?? e.message); e.preventDefault(); };

beforeEach(() => {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  errors.length = 0;
  window.addEventListener('error', onWindowError);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  window.removeEventListener('error', onWindowError);
});

const render = async (props: { docKey: string; value: WorklogDocument }) => {
  await act(async () => {
    root.render(<RichEditor docKey={props.docKey} value={props.value} images={null} onChange={() => {}} />);
  });
  await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
};

describe('RichEditor remount safety', () => {
  it('switching docKey and value at the same time (what a save + reload does) does not throw and shows the new content', async () => {
    await render({ docKey: 'bg-p1-1', value: empty() });
    await render({ docKey: 'bg-p1-2', value: doc('저장된 배경') });
    expect(errors).toEqual([]);
    expect(host.querySelector('.ProseMirror')?.textContent).toContain('저장된 배경');
  });

  it('repeated key/value changes keep working', async () => {
    for (let i = 0; i < 4; i++) await render({ docKey: `k${i}`, value: doc(`내용 ${i}`) });
    expect(errors).toEqual([]);
    expect(host.querySelector('.ProseMirror')?.textContent).toContain('내용 3');
  });

  it('same key with externally replaced value updates the content (server reopen) without throwing', async () => {
    await render({ docKey: 'same', value: doc('이전') });
    await render({ docKey: 'same', value: doc('서버에서 다시 열기') });
    expect(errors).toEqual([]);
    expect(host.querySelector('.ProseMirror')?.textContent).toContain('서버에서 다시 열기');
  });
});
