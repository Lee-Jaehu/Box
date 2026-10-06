import { NodeViewWrapper, ReactNodeViewRenderer, type NodeViewProps } from '@tiptap/react';
import { WorklogImage } from './schema';
import { useImageContext } from './context';

function ImageNodeView({ node, deleteNode, editor }: NodeViewProps) {
  const ctx = useImageContext();
  const useId = node.attrs.attachmentUseId as string;
  const use = ctx?.get(useId);
  const error = ctx?.errors[useId];
  const missing = !use?.description.trim();
  return (
    <NodeViewWrapper className="image-node" data-drag-handle>
      {use ? <img src={use.previewUrl} alt={use.description || use.fileName} style={{ maxWidth: node.attrs.width || 360 }} />
        : <div className="image-missing">첨부 파일을 찾을 수 없습니다. 다시 첨부해 주세요.</div>}
      {editor.isEditable && use && (
        <div className="image-meta">
          <input placeholder="제목 (선택)" value={use.title} onChange={(e) => ctx?.setMeta(useId, { title: e.target.value })} />
          <label>
            상세 설명 (필수) — 어떤 내용을 보여주며, 보고에서 강조할 점은 무엇인가요?
            <textarea value={use.description} aria-invalid={missing}
              onChange={(e) => ctx?.setMeta(useId, { description: e.target.value })} />
          </label>
          {(error || missing) && <span className="field-error">{error ?? '이미지 상세 설명을 입력해 주세요.'}</span>}
          <button type="button" onClick={() => deleteNode()}>이미지 제거</button>
        </div>
      )}
    </NodeViewWrapper>
  );
}

export const ImageNode = WorklogImage.extend({
  addNodeView() {
    return ReactNodeViewRenderer(ImageNodeView);
  },
});
