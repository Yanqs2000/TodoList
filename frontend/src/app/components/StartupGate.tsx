import type { ReactNode } from 'react';
import type { BootstrapState } from '../hooks/useBootstrap';
import '../styles/StartupGate.css';
import { useI18n } from '@/features/i18n/I18nProvider';

interface StartupGateProps {
  state: BootstrapState;
  onRetry: () => Promise<void>;
  children: ReactNode;
}

function StartupGate({ state, onRetry, children }: StartupGateProps) {
  const { t } = useI18n();
  if (state.status === 'ready') return children;

  if (state.status === 'loading') {
    return (
      <main className="startup-gate" role="status" aria-live="polite">
        <div className="startup-gate__spinner" aria-hidden="true" />
        <p>{t('startup.loading')}</p>
      </main>
    );
  }

  if (state.status === 'unsupported') {
    return (
      <main className="startup-gate">
        <section className="startup-gate__card">
          <h1>{t('startup.desktopOnly')}</h1>
          <p>{t('startup.desktopOnlyDesc')}</p>
        </section>
      </main>
    );
  }

  return (
    <main className="startup-gate">
      <section className="startup-gate__card" role="alert">
        <h1>{t('startup.failed')}</h1>
        <p>{t('errors.backendUnavailable')}</p>
        <button type="button" onClick={() => void onRetry()}>
          {t('startup.retry')}
        </button>
      </section>
    </main>
  );
}

export default StartupGate;
