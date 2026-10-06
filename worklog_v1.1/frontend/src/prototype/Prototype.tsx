// P0 편집 시제품 하네스 (?proto=1). 서버 저장이 아니라 "문서 JSON 직렬화 → 다시 열기" 왕복만 검증한다.
// 이미지는 브라우저 메모리(object URL)에만 있으며 서버에 업로드되지 않는다.
import { useMemo, useState } from 'react';
import { RichEditor } from '../editor/RichEditor';
import { emptyDocument, missingImageDescriptions, titlePreview, validateDocument, type WorklogDocument } from '../editor/document';
import type { ImageContextValue, ImageUse } from '../editor/context';
import { createId } from "../utils/id";
interface Card { id: string; doc: WorklogDocument }

export function Prototype() {
  const [cards, setCards] = useState<Card[]>([{ id: createId(), doc: emptyDocument() }]);
  const [openId, setOpenId] = useState<string>(cards[0].id);
  const [uses, setUses] = useState<Record<string, ImageUse>>({});
  const [json, setJson] = useState('');
  const [report, setReport] = useState<string[]>([]);

  const images: ImageContextValue = useMemo(() => ({
    get: (id) => uses[id],
    setMeta: (id, patch) => setUses((u) => (u[id] ? { ...u, [id]: { ...u[id], ...patch } } : u)),
    upload: async (file) => {
      if (file.size > 20 * 1024 * 1024) throw new Error('파일당 20MB를 넘을 수 없습니다.');
      const use: ImageUse = { useId: createId(), previewUrl: URL.createObjectURL(file), title: '', description: '', fileName: file.name };
      setUses((u) => ({ ...u, [use.useId]: use }));
      return use;
    },
    errors: {},
  }), [uses]);

  const serialize = () => {
    const payload = { cards: cards.map((c) => c.doc), imageUses: Object.values(uses).map(({ useId, title, description, fileName }) => ({ useId, title, description, fileName })) };
    const text = JSON.stringify(payload, null, 2);
    setJson(text);
    const problems: string[] = [];
    cards.forEach((c, i) => {
      validateDocument(c.doc).forEach((x) => problems.push(`카드 ${i + 1}: ${x.code} ${x.path}`));
      const desc = Object.fromEntries(Object.values(uses).map((u) => [u.useId, u.description]));
      missingImageDescriptions(c.doc.doc, desc).forEach((id) => problems.push(`카드 ${i + 1}: 이미지 설명 누락 (${id.slice(0, 8)})`));
    });
    setReport(problems);
  };

  const reopen = () => {
    const parsed = JSON.parse(json) as { cards: WorklogDocument[]; imageUses: ImageUse[] };
    setCards(parsed.cards.map((doc) => ({ id: createId(), doc })));
    setOpenId('');
  };

  return (
    <main style={{ maxWidth: 960, margin: '0 auto', padding: 16, fontFamily: 'system-ui, "Malgun Gothic", sans-serif' }}>
      <h1>P0 편집 시제품</h1>
      <p><strong>서버에 저장되지 않습니다.</strong> 표·체크리스트·간트·이미지 설명을 직렬화한 뒤 다시 열어 손실 여부를 확인하는 하네스입니다.</p>
      {cards.map((c, i) => (
        <section key={c.id} style={{ marginBottom: 12 }}>
          <header style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
            <button type="button" onClick={() => setOpenId(openId === c.id ? '' : c.id)}>
              {openId === c.id ? '▾' : '▸'} TASK {i + 1}{openId !== c.id && `: ${titlePreview(c.doc.doc) || '(내용 없음)'}`}
            </button>
            <button type="button" onClick={() => setCards((cs) => cs.filter((x) => x.id !== c.id))} disabled={cards.length === 1}>삭제</button>
          </header>
          {openId === c.id && (
            <RichEditor docKey={c.id} value={c.doc} images={images} placeholder={`TASK ${i + 1} 내용`}
              onChange={(doc) => setCards((cs) => cs.map((x) => (x.id === c.id ? { ...x, doc } : x)))} />
          )}
        </section>
      ))}
      <p>
        <button type="button" onClick={() => { const id = createId(); setCards([...cards, { id, doc: emptyDocument() }]); setOpenId(id); }}>+ 다른 업무 기록</button>{' '}
        <button type="button" onClick={serialize}>직렬화 (JSON 보기)</button>{' '}
        <button type="button" onClick={reopen} disabled={!json}>JSON에서 다시 열기</button>
      </p>
      {report.length > 0 && <ul className="field-error">{report.map((r) => <li key={r}>{r}</li>)}</ul>}
      <textarea value={json} onChange={(e) => setJson(e.target.value)} style={{ width: '100%', minHeight: 240, fontFamily: 'monospace' }} aria-label="문서 JSON" />
    </main>
  );
}
