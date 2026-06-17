import type { AchievementState } from '@/shared/types';
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

const DAILY_GOAL = 10;

function Footer({ stats, onClearCompleted, achievements }: FooterProps) {
  const todayCompleted = achievements?.todayCompleted ?? 0;
  const streakDays = achievements?.streakDays ?? 0;

  const handleClearCompleted = () => {
    if (stats.completed === 0) return;
    if (window.confirm(`确定要清除 ${stats.completed} 个已完成的任务吗？`)) {
      onClearCompleted();
    }
  };

  return (
    <div className="footer">
      <div className="footer-stats">
        <div className="footer-stat">
          <ProgressRing current={todayCompleted} goal={DAILY_GOAL} />
          <span className="footer-stat-label">今日目标</span>
        </div>
        <div className="footer-stat">
          <span className="footer-stat-value">{streakDays}</span>
          <span className="footer-stat-label">连续天数</span>
        </div>
        <div className="footer-stat">
          <span className="footer-stat-value">{stats.completed}</span>
          <span className="footer-stat-label">总完成</span>
        </div>
      </div>
      <div className="footer-actions">
        <span className="footer-summary">
          共 {stats.total} 项 · 未完成 {stats.active}
        </span>
        <button
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
