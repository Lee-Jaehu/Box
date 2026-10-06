import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it, vi } from 'vitest';
import { ErrorBoundary } from './ErrorBoundary';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const Boom = ({ boom }: { boom: boolean }) => { if (boom) throw new Error('렌더링 중 예외'); return <p>정상 화면</p>; };

describe('ErrorBoundary', () => {
  it('shows a recoverable message instead of a blank page, and recovers when the route (resetKey) changes', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const host = document.createElement('div');
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => { root.render(<ErrorBoundary resetKey="a"><Boom boom /></ErrorBoundary>); });
    expect(host.textContent).toContain('화면을 표시하는 중 오류가 발생했습니다');
    expect(host.textContent).toContain('렌더링 중 예외');
    await act(async () => { root.render(<ErrorBoundary resetKey="b"><Boom boom={false} /></ErrorBoundary>); });
    expect(host.textContent).toContain('정상 화면');
    await act(async () => root.unmount());
    host.remove();
  });
});
