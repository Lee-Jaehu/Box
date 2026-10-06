import { useEffect, useState } from 'react';
import { ErrorBoundary } from './ErrorBoundary';
import { ActorPicker, SessionProvider, ToastHost, useSession } from './ui';
import { LogsHome } from './features/LogsHome';
import { MastersPage } from './features/MastersPage';
import { OpsPage } from './features/OpsPage';
import { ProjectDetail, ProjectsPage } from './features/ProjectsPage';
import { ReportsPage } from './features/ReportsPage';
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
    return <>{banner}<LogsHome key={query.get('date') ?? 'today'} initialDate={query.get('date') ?? undefined} /></>;
  }
  if (parts[0] === 'todos' || parts[0] === 'issues') return <>{banner}<TrackerWorkspace kind={parts[0]} projectId={parts[1]} /></>;
  if (parts[0] === 'reports') return <>{banner}<ReportsPage /></>;
  if (parts[0] === 'projects' && parts[1]) return <>{banner}<ProjectDetail key={parts[1]} projectId={parts[1]} /></>;
  return <>{banner}<ProjectsPage /></>;
}

export function App() {
  const hash = useHash();
  const top = parseHash(hash).parts[0] || 'logs';
  const link = (key: string, label: string) => <a className={top === key ? 'active' : ''} href={`#/${key}`}>{label}</a>;
  return (
    <ToastHost>
      <SessionProvider>
        <header className="topbar">
          <a className="brand" href="#/logs">Worklog</a>
          <nav>
            {link('logs', '업무일지')}
            {link('todos', 'To-Do')}
            {link('issues', 'Issue')}
            {link('reports', '보고자료')}
            <span className="nav-sep" aria-hidden="true" />
            {link('projects', '프로젝트')}
            {link('masters', '조직·사용자')}
            {link('ops', '운영')}
          </nav>
          <span className="grow" />
          <ActorPicker />
        </header>
        <main className="page"><ErrorBoundary resetKey={hash}><Router /></ErrorBoundary></main>
        <footer className="foot">로그인·권한 기능이 없는 사내 도구입니다. 작성자 선택은 자기신고이며 첨부는 권한으로 보호되지 않습니다.</footer>
      </SessionProvider>
    </ToastHost>
  );
}
