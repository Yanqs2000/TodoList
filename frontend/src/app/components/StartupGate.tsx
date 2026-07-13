import type { ReactNode } from 'react';
import type { BootstrapState } from '../hooks/useBootstrap';
import '../styles/StartupGate.css';

interface StartupGateProps {
  state: BootstrapState;
  onRetry: () => Promise<void>;
  children: ReactNode;
}

function StartupGate({ state, onRetry, children }: StartupGateProps) {
  if (state.status === 'ready') return children;

  if (state.status === 'loading') {
    return (
      <main className="startup-gate" role="status" aria-live="polite">
        <div className="startup-gate__spinner" aria-hidden="true" />
        <p>正在启动本地服务…</p>
      </main>
    );
  }

  if (state.status === 'unsupported') {
    return (
      <main className="startup-gate">
        <section className="startup-gate__card">
          <h1>请通过桌面应用运行</h1>
          <p>此应用的数据由桌面版内置的本地数据库保存，普通浏览器模式不可用。</p>
        </section>
      </main>
    );
  }

  return (
    <main className="startup-gate">
      <section className="startup-gate__card" role="alert">
        <h1>暂时无法打开应用</h1>
        <p>{state.message}</p>
        <button type="button" onClick={() => void onRetry()}>
          重试
        </button>
      </section>
    </main>
  );
}

export default StartupGate;
