import { useEffect, useMemo, useRef, useState } from 'react';
import { EditorContent, useEditor, type Editor } from '@tiptap/react';
import { leaveNodeSelection } from './selection';
import { buildExtensions } from './schema';
import { GanttNode } from './GanttView';
import { ImageNode } from './ImageView';
import { ImageContext, type ImageContextValue } from './context';
import { defaultGanttAttrs, todayLocal } from '../gantt/adapter';
import { wrapDocument, type TiptapNode, type WorklogDocument } from './document';
import './editor.css';

interface Props {
  value: WorklogDocument;
  onChange: (doc: WorklogDocument) => void;
  images: ImageContextValue | null;
  placeholder?: string;
  editable?: boolean;
  /** 같은 에디터를 다른 문서로 재사용하지 않도록 카드별로 바뀌는 키 */
  docKey: string;
}

function TablePicker({ onPick }: { onPick: (rows: number, cols: number) => void }) {
  const [hover, setHover] = useState<[number, number]>([0, 0]);
  return (
    <div className="table-picker" onMouseLeave={() => setHover([0, 0])}>
      <div className="grid">
        {Array.from({ length: 6 }, (_, r) =>
          Array.from({ length: 6 }, (_, c) => (
            <button type="button" key={`${r}-${c}`} aria-label={`${r + 1}행 ${c + 1}열 표`}
              className={r < hover[0] && c < hover[1] ? 'on' : ''}
              onMouseEnter={() => setHover([r + 1, c + 1])}
              onClick={() => onPick(r + 1, c + 1)} />
          )),
        )}
      </div>
      <small>{hover[0] ? `${hover[0]} × ${hover[1]}` : '표 크기 선택'}</small>
    </div>
  );
}

function Toolbar({ editor, images }: { editor: Editor; images: ImageContextValue | null }) {
  const [pickTable, setPickTable] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const inTable = editor.isActive('table');
  const btn = (label: string, active: boolean, run: () => void, title?: string) => (
    <button type="button" className={active ? 'active' : ''} title={title ?? label}
      onMouseDown={(e) => e.preventDefault()} onClick={run}>{label}</button>
  );
  const insertImages = async (files: FileList | null) => {
    if (!files || !images) return;
    setUploadError(null);
    for (const file of Array.from(files)) {
      try {
        const use = await images.upload(file);
        leaveNodeSelection(editor);
        editor.chain().focus().insertContent({ type: 'image', attrs: { attachmentUseId: use.useId } }).run();
      } catch (e) {
        setUploadError(e instanceof Error ? e.message : '이미지 업로드에 실패했습니다.');
      }
    }
    if (fileRef.current) fileRef.current.value = '';
  };
  return (
    <div className="toolbar" role="toolbar" aria-label="서식">
      {btn('B', editor.isActive('bold'), () => editor.chain().focus().toggleBold().run(), '굵게')}
      {btn('I', editor.isActive('italic'), () => editor.chain().focus().toggleItalic().run(), '기울임')}
      {btn('U', editor.isActive('underline'), () => editor.chain().focus().toggleUnderline().run(), '밑줄')}
      {btn('S', editor.isActive('strike'), () => editor.chain().focus().toggleStrike().run(), '취소선')}
      {btn('링크', editor.isActive('link'), () => {
        const href = window.prompt('링크 주소 (http, https, mailto)');
        if (href) editor.chain().focus().extendMarkRange('link').setLink({ href }).run();
        else editor.chain().focus().unsetLink().run();
      })}
      <span className="sep" />
      {btn('제목', editor.isActive('heading', { level: 2 }), () => editor.chain().focus().toggleHeading({ level: 2 }).run())}
      {btn('• 목록', editor.isActive('bulletList'), () => editor.chain().focus().toggleBulletList().run())}
      {btn('1. 번호', editor.isActive('orderedList'), () => editor.chain().focus().toggleOrderedList().run())}
      {btn('☑ 체크리스트', editor.isActive('taskList'), () => editor.chain().focus().toggleTaskList().run())}
      <span className="sep" />
      <span className="rel">
        {btn('표', pickTable, () => setPickTable((v) => !v), '표 삽입')}
        {pickTable && (
          <TablePicker onPick={(rows, cols) => {
            leaveNodeSelection(editor);
            editor.chain().focus().insertTable({ rows, cols, withHeaderRow: true }).run();
            setPickTable(false);
          }} />
        )}
      </span>
      {inTable && (
        <>
          {btn('행+', false, () => editor.chain().focus().addRowAfter().run(), '아래에 행 추가')}
          {btn('행−', false, () => editor.chain().focus().deleteRow().run(), '행 삭제')}
          {btn('열+', false, () => editor.chain().focus().addColumnAfter().run(), '오른쪽에 열 추가')}
          {btn('열−', false, () => editor.chain().focus().deleteColumn().run(), '열 삭제')}
          {btn('병합', false, () => editor.chain().focus().mergeCells().run(), '선택한 셀 병합')}
          {btn('분할', false, () => editor.chain().focus().splitCell().run(), '셀 분할')}
          {btn('표 삭제', false, () => editor.chain().focus().deleteTable().run())}
        </>
      )}
      <span className="sep" />
      {btn('간트', false, () => {
        leaveNodeSelection(editor);
        editor.chain().focus().insertContent({ type: 'gantt', attrs: defaultGanttAttrs(todayLocal()) }).run();
      }, '간트 삽입')}
      {images && (
        <>
          {btn('이미지', false, () => fileRef.current?.click(), '이미지 첨부 (PNG/JPEG/WebP)')}
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" multiple hidden
            onChange={(e) => void insertImages(e.target.files)} />
        </>
      )}
      {uploadError && <span className="field-error">{uploadError}</span>}
    </div>
  );
}

export function RichEditor({ value, onChange, images, placeholder, editable = true, docKey }: Props) {
  const extensions = useMemo(() => buildExtensions({ gantt: GanttNode, image: ImageNode }), []);
  const lastEmitted = useRef<string>(JSON.stringify(value.doc));
  const editorRef = useRef<Editor | null>(null);
  const insertDroppedImages = (list: FileList | undefined | null, event: Event): boolean => {
    const files = Array.from(list ?? []).filter((f) => f.type.startsWith('image/'));
    if (!files.length || !images) return false;
    event.preventDefault();
    void (async () => {
      for (const f of files) {
        const use = await images.upload(f).catch(() => null);
        const ed = editorRef.current;
        if (use && ed) {
          leaveNodeSelection(ed);
          ed.chain().focus().insertContent({ type: 'image', attrs: { attachmentUseId: use.useId } }).run();
        }
      }
    })();
    return true;
  };
  const editor = useEditor({
    extensions,
    content: value.doc,
    editable,
    editorProps: {
      attributes: { class: 'editor-surface', 'aria-label': placeholder ?? '내용', lang: 'ko' },
      handleDrop: (_view, event) => insertDroppedImages(event.dataTransfer?.files, event),
      handlePaste: (_view, event) => insertDroppedImages(event.clipboardData?.files, event),
    },
    onUpdate: ({ editor: ed }) => {
      const json = ed.getJSON() as TiptapNode;
      const serialized = JSON.stringify(json);
      if (serialized === lastEmitted.current) return; // 내용이 같은 update(마운트 정규화 등)는 변경으로 보지 않는다
      lastEmitted.current = serialized;
      onChange(wrapDocument(json));
    },
  }, [docKey]);

  // docKey 가 바뀌면 useEditor 가 이전 에디터를 destroy 하고 새로 만든다. 그 사이 렌더에서는 파괴된 에디터가 넘어올 수 있으므로
  // (저장 → 목록 재로드 때 docKey/value 가 함께 바뀜) 파괴된 에디터의 commands 등에는 절대 접근하지 않는다.
  useEffect(() => {
    editorRef.current = editor && !editor.isDestroyed ? editor : null;
    if (editor && !editor.isDestroyed) editor.setEditable(editable);
  }, [editor, editable]);

  // 외부에서 문서가 교체된 경우(서버 재열기, 초안 복구)에만 반영한다. 입력 중에는 덮어쓰지 않는다.
  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    const incoming = JSON.stringify(value.doc);
    if (incoming !== lastEmitted.current) {
      lastEmitted.current = incoming;
      editor.commands.setContent(value.doc, { emitUpdate: false });
    }
  }, [editor, value.doc]);

  if (!editor) return null;
  return (
    <ImageContext.Provider value={images}>
      <div className="rich-editor">
        {editable && <Toolbar editor={editor} images={images} />}
        <EditorContent editor={editor} />
      </div>
    </ImageContext.Provider>
  );
}
