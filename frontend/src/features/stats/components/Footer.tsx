import type { AchievementState } from '@/shared/types';
import { DAILY_GOAL } from '@/shared/constants';
import { useConfirm } from '@/shared/components/ConfirmDialog';
import ProgressRing from './ProgressRing';
import '../styles/Footer.css';
import { useI18n } from '@/features/i18n/I18nProvider';

interface FooterProps {
  stats: {
    total: number;
    active: number;
    completed: number;
  };
  onClearCompleted: () => Promise<void>;
  achievements?: AchievementState;
  clearPending?: boolean;
  clearDisabled?: boolean;
}

function Footer({ stats, onClearCompleted, achievements, clearPending = false, clearDisabled = false }: FooterProps) {
  const todayCompleted = achievements?.todayCompleted ?? 0;
  const streakDays = achievements?.streakDays ?? 0;
  const confirm = useConfirm();
  const { t } = useI18n();

  const handleClearCompleted = async () => {
    if (stats.completed === 0) return;
    const ok = await confirm({
      title: t('footer.clearTitle'),
      message: t('footer.clearMessage', { count: stats.completed }),
      confirmText: t('time.clear'),
      danger: true,
    });
    if (ok) await onClearCompleted();
  };

  return (
    <div className="footer">
      <div className="footer-grid">
        <div className="footer-card">
          <ProgressRing current={todayCompleted} goal={DAILY_GOAL} size={56} strokeWidth={5} />
          <div className="footer-card__meta">
            <span className="footer-card__label">{t('footer.todayGoal')}</span>
            <span className="footer-card__sub">{todayCompleted} / {DAILY_GOAL}</span>
          </div>
        </div>

        <div className="footer-card">
          <div className="footer-card__big">
            <span className="footer-card__value">{streakDays}</span>
            <span className="footer-card__unit">{t('footer.days')}</span>
          </div>
          <div className="footer-card__meta">
            <span className="footer-card__label">{t('footer.streak')}</span>
            <span className="footer-card__sub">{t('footer.uninterrupted')}</span>
          </div>
        </div>

        <div className="footer-card">
          <div className="footer-card__big">
            <span className="footer-card__value">{stats.completed}</span>
          </div>
          <div className="footer-card__meta">
            <span className="footer-card__label">{t('footer.totalCompleted')}</span>
            <span className="footer-card__sub">{t('footer.summary', { total: stats.total, active: stats.active })}</span>
          </div>
        </div>
      </div>

      <div className="footer-actions">
        <button
          type="button"
          className="btn-clear"
          disabled={stats.completed === 0 || clearPending || clearDisabled}
          onClick={handleClearCompleted}
        >
          {t('footer.clear')}
        </button>
      </div>
    </div>
  );
}

export default Footer;
