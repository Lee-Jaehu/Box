import { useEffect, useState } from 'react';
import { ErrorBoundary } from './ErrorBoundary';
import { ActorPicker, SessionProvider, ToastHost, useSession } from './ui';
import { LogsHome } from './features/LogsHome';
import { MastersPage } from './features/MastersPage';
import { OpsPage } from './features/OpsPage';
import { ProjectDetail, ProjectsPage } from './features/ProjectsPage';
import { ProjectWorkBar } from './features/ProjectWorkBar';
import { ReportsPage, type Template } from './features/ReportsPage';
import { SideNav } from './features/SideNav';
import { LogEditorPage, TrackerWorkspace } from './features/WorkspacePage';
import './app.css';

const DEFAULT_HASH = '#/logs';

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
    const project = query.get('project') ?? undefined;  // 왼쪽 트리 PJT ▸ Worklog
    return (
      <>
        {banner}
        {project && <ProjectWorkBar projectId={project} tab="logs" />}
        <LogsHome key={`${project ?? ''}|${query.get('date') ?? 'today'}`} initialDate={query.get('date') ?? undefined} projectId={project} />
      </>
    );
  }
  if (parts[0] === 'todos' || parts[0] === 'issues') {
    return <>{banner}{parts[1] && <ProjectWorkBar projectId={parts[1]} tab={parts[0]} />}<TrackerWorkspace kind={parts[0]} projectId={parts[1]} /></>;
  }
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
  return (
    <ToastHost>
      <SessionProvider>
        <header className="topbar">
          <button type="button" className="menu-btn" aria-label="메뉴" aria-expanded={drawer} onClick={() => setDrawer((v) => !v)}>☰</button>
          <a className="brand" href="#/logs">Worklog</a>
          <span className="grow" />
          <ActorPicker />
        </header>
        <div className={`shell${drawer ? ' drawer-open' : ''}`}>
          <aside className="sidenav-wrap"><ErrorBoundary resetKey="nav"><SideNav hash={hash} onNavigate={() => setDrawer(false)} /></ErrorBoundary></aside>
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
