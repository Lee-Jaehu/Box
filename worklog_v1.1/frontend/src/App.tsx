import { useEffect, useState } from 'react';
import { ErrorBoundary } from './ErrorBoundary';
import { ActorPicker, SessionProvider, ToastHost, useSession } from './ui';
import { LogsHome } from './features/LogsHome';
import { MastersPage } from './features/MastersPage';
import { OpsPage } from './features/OpsPage';
import { ProjectDetail, ProjectsPage } from './features/ProjectsPage';
import { ProjectWorklog } from './features/ProjectWorklog';
import { ReportsPage, type Template } from './features/ReportsPage';
import { SideNav } from './features/SideNav';
import { LogEditorPage, TrackerWorkspace } from './features/WorkspacePage';
import './app.css';

const DEFAULT_HASH = '#/logs';
const COLLAPSE_KEY = 'worklog.navCollapsed';
const NARROW = '(max-width: 860px)';  // app.css 서랍 전환 기준과 같게

function useHash(): string {
  const [h, setH] = useState(window.location.hash || DEFAULT_HASH);
  useEffect(() => {
    const f = () => setH(window.location.hash || DEFAULT_HASH);
    window.addEventListener('hashchange', f);
    return () => window.removeEventListener('hashchange', f);
  }, []);
  return h;
}

/** '#/logs/<프로젝트>/<날짜>?date=...' → { parts: ['logs', <프로젝트>, <날짜>], query } */
export function parseHash(hash: string): { parts: string[]; query: URLSearchParams } {
  const [path, qs = ''] = hash.replace(/^#\/?/, '').split('?');
  return { parts: path.split('/').filter((p, i) => p !== '' || i === 0), query: new URLSearchParams(qs) };
}

function Router() {
  const { ready, users, actor } = useSession();
  const hash = useHash();
  const { parts, query } = parseHash(hash);
  if (!ready) return <p className="hint">불러오는 중…</p>;

  // 예전 주소(#/projects/<id>/log|todo|issue|info) 호환
  if (parts[0] === 'projects' && parts[1] && parts[2]) {
    const to = { log: 'logs', todo: 'todos', issue: 'issues' }[parts[2]];
    window.location.replace(to && to !== 'logs' ? `#/${to}/${parts[1]}` : to === 'logs' ? `#/logs/${parts[1]}/${new Date().toLocaleDateString('sv-SE')}` : `#/projects/${parts[1]}`);
    return null;
  }
  if (parts[0] === 'masters') return <MastersPage />;
  if (parts[0] === 'ops') return <OpsPage />;

  const banner = users.length === 0
    ? <div className="notice">등록된 사용자가 없습니다. 먼저 <a href="#/masters">조직·사용자</a>에서 조직과 사용자를 등록하거나 Excel/CSV로 가져오세요.</div>
    : !actor
      ? <div className="notice">저장하려면 상단에서 <strong>작성자</strong>를 먼저 선택해 주세요. 변경자를 기록하기 위한 설정이며 로그인이 아닙니다.</div>
      : null;

  if (parts[0] === 'logs') {
    if (parts[1]) return <>{banner}<LogEditorPage key={parts[1]} projectId={parts[1]} date={parts[2]} /></>;
    const project = query.get('project');  // 왼쪽 트리 PJT ▸ 전체 Worklog / User ▸ Worklog (To-Do·Issue 포함)
    if (project) {
      return <>{banner}<ProjectWorklog key={project} projectId={project} authorId={query.get('author') ?? undefined} initialDate={query.get('date') ?? undefined} /></>;
    }
    return <>{banner}<LogsHome key={query.get('date') ?? 'today'} initialDate={query.get('date') ?? undefined} /></>;
  }
  if (parts[0] === 'todos' || parts[0] === 'issues') return <>{banner}<TrackerWorkspace kind={parts[0]} projectId={parts[1]} /></>;  // 옛 주소
  if (parts[0] === 'reports') {
    const project = query.get('project');  // 왼쪽 트리 PJT ▸ 자료 생성기 ▸ 주간업무자료 / 경영진보고자료
    const template = query.get('template');
    return (
      <>
        {banner}
        <ReportsPage key={hash} initialProjectIds={project ? [project] : undefined}
          initialTemplate={template === 'weekly' || template === 'exec' ? template as Template : undefined} />
      </>
    );
  }
  if (parts[0] === 'projects' && parts[1]) return <>{banner}<ProjectDetail key={parts[1]} projectId={parts[1]} /></>;
  return <>{banner}<ProjectsPage /></>;
}

/** 화면 틀: 위 = 로고·작성자, 왼쪽 = 담당 ▸ 팀 ▸ PJT 트리(SideNav), 오른쪽 = 기존 화면 (결정 I37, 상단 탭 대체) */
export function App() {
  const hash = useHash();
  const [drawer, setDrawer] = useState(false);  // 좁은 화면에서 왼쪽 트리를 서랍처럼 연다
  const [collapsed, setCollapsed] = useState<boolean>(() => { try { return localStorage.getItem(COLLAPSE_KEY) === '1'; } catch { return false; } });
  useEffect(() => {
    try { localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0'); } catch { /* 무시 */ }
    // 폭이 바뀌는 전환(.2s)이 끝나면 resize를 알려 간트 등 폭을 재는 화면이 다시 그리게 한다
    const t = window.setTimeout(() => window.dispatchEvent(new Event('resize')), 260);
    return () => window.clearTimeout(t);
  }, [collapsed]);
  // ☰: 좁은 화면이면 서랍 열기·닫기, 넓은 화면이면 트리 접기·펴기
  const menu = () => (window.matchMedia?.(NARROW).matches ? setDrawer((v) => !v) : setCollapsed((v) => !v));
  return (
    <ToastHost>
      <SessionProvider>
        <header className="topbar">
          <button type="button" className="menu-btn" aria-label="왼쪽 트리 접기·펴기" title="왼쪽 트리 접기·펴기" onClick={menu}>☰</button>
          <a className="brand" href="#/logs">Worklog</a>
          <span className="grow" />
          <ActorPicker />
        </header>
        <div className={`shell${drawer ? ' drawer-open' : ''}${collapsed ? ' nav-collapsed' : ''}`}>
          <aside className="sidenav-wrap"><ErrorBoundary resetKey="nav"><SideNav hash={hash} onNavigate={() => setDrawer(false)} collapsed={collapsed && !drawer} onCollapse={setCollapsed} /></ErrorBoundary></aside>
          {drawer && <div className="drawer-mask" onClick={() => setDrawer(false)} aria-hidden="true" />}
          <div className="main-col">
            <main className="page"><ErrorBoundary resetKey={hash}><Router /></ErrorBoundary></main>
            <footer className="foot">로그인·권한 기능이 없는 사내 도구입니다. 작성자 선택은 자기신고이며 첨부는 권한으로 보호되지 않습니다.</footer>
          </div>
        </div>
      </SessionProvider>
    </ToastHost>
  );
}
