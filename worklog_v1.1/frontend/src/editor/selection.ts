import type { Editor } from '@tiptap/core';
import { NodeSelection } from '@tiptap/pm/state';

/** 간트·이미지 같은 atom node가 선택된 채로 삽입하면 선택 node가 대체되어 사라진다. 뒤에 빈 문단을 만들어 커서를 옮긴다. */
export function leaveNodeSelection(editor: Editor): void {
  const { selection } = editor.state;
  if (selection instanceof NodeSelection) {
    const pos = selection.to;
    editor.chain().insertContentAt(pos, { type: 'paragraph' }).setTextSelection(pos + 1).run();
  }
}
