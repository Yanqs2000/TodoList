import type { AchievementDef, AchievementState } from '@/shared/types';
import '../styles/AchievementDrawer.css';
import { useI18n } from '@/features/i18n/I18nProvider';

interface AchievementDrawerProps {
  open: boolean;
  onClose: () => void;
  achievements: AchievementState;
  allAchievements: AchievementDef[];
}

function AchievementDrawer({ open, onClose, achievements, allAchievements }: AchievementDrawerProps) {
  const { t } = useI18n();
  if (!open) return null;

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <div className="drawer">
        <div className="drawer-header">
          <h2>{t('header.achievements')}</h2>
          <button className="icon-btn" onClick={onClose} aria-label={t('common.close')}>
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="drawer-stats">
          <div className="stat-item">
            <span className="stat-value">{achievements.streakDays}</span>
            <span className="stat-label">{t('achievement.streakDays')}</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{achievements.todayCompleted}</span>
            <span className="stat-label">{t('achievement.today')}</span>
          </div>
        </div>
        <div className="achievement-list">
          {allAchievements.map(a => {
            const unlocked = achievements.unlocked.includes(a.id);
            return (
              <div key={a.id} className={`achievement-card${unlocked ? ' unlocked' : ''}`}>
                <span className="achievement-icon">{unlocked ? a.icon : '🔒'}</span>
                <div className="achievement-info">
                  <strong>{a.name}</strong>
                  <span>{a.description}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}

export default AchievementDrawer;
