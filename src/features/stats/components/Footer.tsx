import type { AchievementState } from '@/shared/types';
import { DAILY_GOAL } from '@/shared/constants';
import { useConfirm } from '@/shared/components/ConfirmDialog';
import ProgressRing from './ProgressRing';
import '../styles/Footer.css';

interface FooterProps {
  stats: {
    total: number;
    active: number;
    completed: number;
  };
  onClearCompleted: () => void;
  achievements?: AchievementState;
}

function Footer({ stats, onClearCompleted, achievements }: FooterProps) {
  const todayCompleted = achievements?.todayCompleted ?? 0;
  const streakDays = achievements?.streakDays ?? 0;
  const confirm = useConfirm();

  const handleClearCompleted = async () => {
    if (stats.completed === 0) return;
    const ok = await confirm({
      title: '清除已完成任务',
      message: `确定要清除 ${stats.completed} 个已完成的任务吗？此操作不可撤销。`,
      confirmText: '清除',
      danger: true,
    });
    if (ok) onClearCompleted();
  };

  return (
    <div className="footer">
      <div className="footer-grid">
        <div className="footer-card">
          <ProgressRing current={todayCompleted} goal={DAILY_GOAL} size={56} strokeWidth={5} />
          <div className="footer-card__meta">
            <span className="footer-card__label">今日目标</span>
            <span className="footer-card__sub">{todayCompleted} / {DAILY_GOAL}</span>
          </div>
        </div>

        <div className="footer-card">
          <div className="footer-card__big">
            <span className="footer-card__value">{streakDays}</span>
            <span className="footer-card__unit">天</span>
          </div>
          <div className="footer-card__meta">
            <span className="footer-card__label">连续打卡</span>
            <span className="footer-card__sub">不间断</span>
          </div>
        </div>

        <div className="footer-card">
          <div className="footer-card__big">
            <span className="footer-card__value">{stats.completed}</span>
          </div>
          <div className="footer-card__meta">
            <span className="footer-card__label">总完成</span>
            <span className="footer-card__sub">共 {stats.total} 项 · 进行中 {stats.active}</span>
          </div>
        </div>
      </div>

      <div className="footer-actions">
        <button
          type="button"
          className="btn-clear"
          disabled={stats.completed === 0}
          onClick={handleClearCompleted}
        >
          清除已完成
        </button>
      </div>
    </div>
  );
}

export default Footer;
