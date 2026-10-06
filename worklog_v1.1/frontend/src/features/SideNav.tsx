/** 왼쪽 세로 트리 내비게이션 (Windows 탐색기 왼쪽 창처럼): 담당 ▸ 팀 ▸ PJT ▸ 전체 Worklog / User ▸ Worklog / 자료 생성기.
 *  Worklog 화면 안에 To-Do·Issue가 함께 있다. 오른쪽 화면은 기존 주소(#/projects/<id>, #/logs?project=&author=, #/reports?project=)를 연다. 결정 I37. */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api } from '../api/client';
import type { List } from '../api/types';
import { errText, STATUS_LABEL, useSession } from '../ui';
import { activeKeys, buildTree, filterTree, GLOBAL_LINKS, href, isProjectDone, key, milestoneLabel, peopleOf, ROLE_LABEL, type NavProject } from './navTree';

const OPEN_KEY = 'worklog.navOpen';
const MINE_KEY = 'worklog.navMine';

function loadOpen(): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem(OPEN_KEY) || '[]') as string[]); } catch { return new Set(); }
}

/** 과제 목록 전체 (200개씩 nextCursor 끝까지) */
export async function fetchAllProjects(): Promise<NavProject[]> {
  const out: NavProject[] = [];
  let cursor: string | null = null;
  for (let i = 0; i < 50; i += 1) {
    const page: List<NavProject> = await api.get<List<NavProject>>(`/projects?limit=200${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`);
    out.push(...page.items);
    if (!page.nextCursor) break;
    cursor = page.nextCursor;
  }
  return out;
}

interface RowProps {
  depth: number; label: ReactNode; nodeKey: string; selected: string | null; expanded?: boolean;
  link?: string; title?: string; className?: string; onToggle?: (k: string, open?: boolean) => void; onNavigate?: () => void;
}

function Row({ depth, label, nodeKey, selected, expanded, link, title, className, onToggle, onNavigate }: RowProps) {
  const hasChildren = expanded !== undefined;
  const caret = hasChildren
    ? <button type="button" className="tree-caret" aria-label={expanded ? '접기' : '펴기'} onClick={(e) => { e.preventDefault(); e.stopPropagation(); onToggle?.(nodeKey); }}>{expanded ? '▾' : '▸'}</button>
    : <span className="tree-caret" aria-hidden="true" />;
  const cls = `tree-row${selected === nodeKey ? ' active' : ''}${className ? ` ${className}` : ''}`;
  const style = { paddingLeft: 6 + depth * 14 };
  const common = { className: cls, style, title, role: 'treeitem', 'aria-expanded': hasChildren ? expanded : undefined, 'aria-selected': selected === nodeKey, 'data-key': nodeKey };
  if (link) {
    return (
      <a {...common} href={link} onClick={() => { if (hasChildren) onToggle?.(nodeKey, true); onNavigate?.(); }}>
        {caret}<span className="tree-label">{label}</span>
      </a>
    );
  }
  return (
    <div {...common} onClick={() => onToggle?.(nodeKey)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggle?.(nodeKey); } }} tabIndex={0}>
      {caret}<span className="tree-label">{label}</span>
    </div>
  );
}

export function SideNav({ hash, onNavigate, projects: given, collapsed = false, onCollapse }: {
  hash: string; onNavigate?: () => void; projects?: NavProject[];
  collapsed?: boolean; onCollapse?: (collapsed: boolean) => void;  // 넓은 화면에서 트리 접기·펴기 (App이 상태를 가진다)
}) {
  const { actor } = useSession();
  const [projects, setProjects] = useState<NavProject[] | null>(given ?? null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (given) return;
    try { setProjects(await fetchAllProjects()); setError(null); } catch (e) { setError(errText(e)); }
  }, [given]);
  useEffect(() => { void load(); }, [load]);
  // 프로젝트·조직 화면에서 다른 곳으로 가면(만들기·수정 뒤) 목록을 다시 읽는다
  const prev = useRef(hash);
  useEffect(() => {
    if (prev.current !== hash && /^#\/(projects|masters)/.test(prev.current)) void load();
    prev.current = hash;
  }, [hash, load]);

  const [open, setOpen] = useState<Set<string>>(loadOpen);
  useEffect(() => { try { localStorage.setItem(OPEN_KEY, JSON.stringify([...open])); } catch { /* 무시 */ } }, [open]);
  const [q, setQ] = useState('');
  const [mine, setMine] = useState<boolean>(() => { try { return localStorage.getItem(MINE_KEY) === '1'; } catch { return false; } });
  useEffect(() => { try { localStorage.setItem(MINE_KEY, mine ? '1' : '0'); } catch { /* 무시 */ } }, [mine]);

  const all = useMemo(() => projects ?? [], [projects]);
  const active = useMemo(() => activeKeys(hash, all), [hash, all]);
  const activeOpen = active.open.join('|');
  useEffect(() => {  // 지금 주소의 경로는 자동으로 편다
    if (!activeOpen) return;
    setOpen((s) => { const n = new Set(s); activeOpen.split('|').forEach((k) => n.add(k)); return n.size === s.size ? s : n; });
  }, [activeOpen]);

  const toggle = (k: string, force?: boolean) => setOpen((s) => {
    const n = new Set(s);
    if (force ?? !n.has(k)) n.add(k); else n.delete(k);
    return n;
  });
  const searching = q.trim() !== '';
  const isOpen = (k: string) => (searching && (k.startsWith('d:') || k.startsWith('t:'))) || open.has(k);
  const tree = useMemo(() => filterTree(buildTree(all), q, mine && actor ? actor.id : null), [all, q, mine, actor]);
  const sel = active.selected;
  const row = { selected: sel, onToggle: toggle, onNavigate };

  if (collapsed) {
    return (
      <nav className="sidenav rail" aria-label="프로젝트 탐색 (접힘)">
        <button type="button" className="rail-btn" title="트리 펴기" aria-label="트리 펴기" onClick={() => onCollapse?.(false)}>»</button>
      </nav>
    );
  }

  return (
    <nav className="sidenav" aria-label="프로젝트 탐색">
      <div className="sidenav-tools">
        <div className="row between tight sidenav-head">
          <strong className="hint">담당 ▸ 팀 ▸ 과제</strong>
          {onCollapse && <button type="button" className="rail-btn" title="트리 접기 (오른쪽 화면을 넓게)" aria-label="트리 접기" onClick={() => onCollapse(true)}>«</button>}
        </div>
        <input type="search" placeholder="과제·팀 이름 검색" value={q} onChange={(e) => setQ(e.target.value)} aria-label="트리 검색" />
        <div className="row between tight">
          <label className="check hint"><input type="checkbox" checked={mine} disabled={!actor} onChange={(e) => setMine(e.target.checked)} /> 내 프로젝트만</label>
          <span>
            <button type="button" className="link" title="모두 접기" onClick={() => setOpen(new Set())}>접기</button>
            <button type="button" className="link" title="목록 새로고침" onClick={() => void load()}>새로고침</button>
          </span>
        </div>
      </div>
      <div className="tree" role="tree">
        {error && <p className="field-error">{error}</p>}
        {!projects && !error && <p className="hint">불러오는 중…</p>}
        {projects && tree.length === 0 && <p className="hint">{all.length === 0 ? '등록된 프로젝트가 없습니다.' : '조건에 맞는 프로젝트가 없습니다.'}</p>}
        {tree.map((d) => (
          <div key={d.key} role="group">
            <Row depth={0} nodeKey={d.key} expanded={isOpen(d.key)} label={<strong>{d.name}</strong>} className="tree-division" {...row} />
            {isOpen(d.key) && d.teams.map((t) => (
              <div key={t.key} role="group">
                <Row depth={1} nodeKey={t.key} expanded={isOpen(t.key)} label={<>{t.name} <span className="tree-count">{t.projects.length}</span></>} className="tree-team" {...row} />
                {isOpen(t.key) && t.projects.map((p) => {
                  const done = isProjectDone(p);
                  const pk = key.project(p.id);
                  return (
                    <div key={p.id} role="group">
                      <Row depth={2} nodeKey={pk} expanded={isOpen(pk)} link={href.project(p.id)} className={`tree-project${done ? ' done' : ''}`}
                        title={`${p.name}\n${milestoneLabel(p)} · 상태 ${STATUS_LABEL[p.status] ?? p.status}`}
                        label={<>{p.name}{done ? <span className="tree-tag">완료</span> : p.status === 'on_hold' ? <span className="tree-tag hold">보류</span> : p.status === 'cancelled' ? <span className="tree-tag">취소</span> : null}</>}
                        {...row} />
                      {isOpen(pk) && (
                        <>
                          <Row depth={3} nodeKey={key.worklog(p.id)} link={href.worklog(p.id)} label="전체 Worklog" title="이 과제의 모든 사람 일지 + To-Do·Issue" {...row} />
                          {peopleOf(p).map((person) => {
                            const uk = key.person(p.id, person.id);
                            return (
                              <div key={person.id} role="group">
                                <Row depth={3} nodeKey={uk} expanded={isOpen(uk)} className="tree-person"
                                  label={<>{person.name ?? person.id}{person.role !== 'member' && <span className={`tree-tag role-${person.role}`}>{ROLE_LABEL[person.role]}</span>}</>}
                                  {...row} />
                                {isOpen(uk) && (
                                  <Row depth={4} nodeKey={key.personWorklog(p.id, person.id)} link={href.personWorklog(p.id, person.id)} label="Worklog"
                                    title={`${person.name ?? ''}의 일지 + 담당 To-Do·Issue`} {...row} />
                                )}
                              </div>
                            );
                          })}
                          <Row depth={3} nodeKey={key.reports(p.id)} expanded={isOpen(key.reports(p.id))} link={href.reports(p.id)} label="자료 생성기" {...row} />
                          {isOpen(key.reports(p.id)) && (
                            <>
                              <Row depth={4} nodeKey={key.reportWeekly(p.id)} link={href.reportWeekly(p.id)} label="주간업무자료" {...row} />
                              <Row depth={4} nodeKey={key.reportExec(p.id)} link={href.reportExec(p.id)} label="경영진보고자료" {...row} />
                            </>
                          )}
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="sidenav-global">
        <div className="hint">전체 보기·관리</div>
        {GLOBAL_LINKS.map((g) => (
          <a key={g.key} href={g.href} className={`tree-row global${sel === g.key ? ' active' : ''}`} data-key={g.key} onClick={() => onNavigate?.()}>{g.label}</a>
        ))}
      </div>
    </nav>
  );
}
