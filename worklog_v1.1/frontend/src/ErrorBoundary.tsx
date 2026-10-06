import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props { children: ReactNode; resetKey?: string }
interface State { error: Error | null }

/** 화면 한 곳의 렌더링 예외가 앱 전체를 빈 화면으로 만들지 않도록 막는다. 입력 중이던 일지는 브라우저 임시저장에 남아 있다. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('화면 오류', error, info.componentStack);
  }

  componentDidUpdate(prev: Props): void {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null }); // 다른 화면으로 이동하면 복구
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div className="notice warn" role="alert">
        <h3>화면을 표시하는 중 오류가 발생했습니다</h3>
        <p>저장된 데이터는 안전합니다. 일지를 작성 중이었다면 입력한 내용은 브라우저에 임시저장되어 있어 다시 열면 복구됩니다.</p>
        <div className="row">
          <button type="button" className="primary" onClick={() => window.location.reload()}>새로고침</button>
          <button type="button" onClick={() => this.setState({ error: null })}>다시 시도</button>
          <a className="btn" href="#/logs">업무일지 첫 화면으로</a>
        </div>
        <details><summary>기술 정보 (문의 시 함께 전달)</summary><pre className="plain">{String(this.state.error.stack ?? this.state.error.message)}</pre></details>
      </div>
    );
  }
}
