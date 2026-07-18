import type { Todo } from '@/shared/types';
import { formatTimeField } from '../lib/formatTime';
import { proximityOf, isToday, toTimelineX, type Proximity } from '../lib/timeProximity';
import '../styles/DayTimeline.css';
import { useI18n } from '@/features/i18n/I18nProvider';
import type { TranslationKey } from '@/features/i18n/translations';

const MIN_WIDTH_PCT = 3; // narrowest a point-task block can be (% of track)
const TICK_HOURS = [6, 8, 10, 12, 14, 16, 18, 20, 22];

interface DayTimelineProps {
  tasks: Todo[];
  selectedTaskId?: string | null;
  onSelectTask?: (id: string | null) => void;
  /** Override "now" for testing; live Date.now() when omitted. */
  now?: number;
}

const PROX_LABEL: Record<Proximity, TranslationKey> = {
  overdue: 'timeline.overdue', soon: 'timeline.soon', today: 'timeline.today',
  future: 'timeline.future', none: 'timeline.none',
};

function nowToX(now: number): number | null {
  const d = new Date(now);
  const hours = d.getHours() + d.getMinutes() / 60;
  // Only show the now-line while "now" is inside the 06:00–24:00 window.
  if (hours < 6 || hours > 24) return null;
  const x = ((hours - 6) / 18) * 100;
  return x > 100 ? null : x;
}

function DayTimeline({ tasks, selectedTaskId, onSelectTask, now: nowProp }: DayTimelineProps) {
  const { t, locale } = useI18n();
  const now = nowProp ?? Date.now();

  const todayTimed = tasks.filter(t => t.time?.start && isToday(t.time.start, now));
  const unscheduledN = tasks.filter(t => !t.time?.start).length;

  const blocks = todayTimed.map(t => {
    const startX = toTimelineX(t.time!.start) ?? 0;
    let endX: number | null = null;
    if (t.time!.end) {
      endX = isToday(t.time!.end, now) ? (toTimelineX(t.time!.end) ?? startX) : 100;
    }
    const width = endX !== null ? Math.max(endX - startX, MIN_WIDTH_PCT) : MIN_WIDTH_PCT;
    const prox = proximityOf(t.time, now);
    return { task: t, left: startX, width, prox };
  });

  const nowX = nowToX(now);

  return (
    <section className="day-timeline" role="region" aria-label={t('timeline.title')}>
      <div className="day-timeline__header">
        <span className="day-timeline__title">{t('timeline.title')}</span>
        {unscheduledN > 0 && (
          <span className="day-timeline__cluster" title={t('timeline.unscheduledTitle')}>{t('timeline.unscheduled', { count: unscheduledN })}</span>
        )}
      </div>

      <div className="day-timeline__track" role="presentation">
        {TICK_HOURS.map(h => (
          <span
            key={h}
            className="day-timeline__tick"
            style={{ left: `${((h - 6) / 18) * 100}%` }}
          >
            <span className="day-timeline__tick-mark" aria-hidden="true" />
            <span className="day-timeline__tick-label">{h}</span>
          </span>
        ))}

        {nowX !== null && (
          <div className="day-timeline__now" style={{ left: `${nowX}%` }} aria-hidden="true">
            <span className="day-timeline__now-dot" />
          </div>
        )}

        {blocks.map(({ task, left, width, prox }) => (
          <button
            key={task.id}
            type="button"
            className={`day-timeline__block day-timeline__block--${prox}${selectedTaskId === task.id ? ' is-selected' : ''}`}
            style={{ left: `${left}%`, width: `${width}%` }}
            title={`${task.text} · ${formatTimeField(task.time!, locale)}`}
            aria-label={`${task.text}, ${formatTimeField(task.time!, locale)}, ${t(PROX_LABEL[prox])}`}
            aria-pressed={selectedTaskId === task.id}
            onClick={() => onSelectTask?.(selectedTaskId === task.id ? null : task.id)}
          >
            <span className="day-timeline__block-label">{task.text}</span>
          </button>
        ))}

        {todayTimed.length === 0 && (
          <div className="day-timeline__empty">{t('timeline.empty')}</div>
        )}
      </div>
    </section>
  );
}

export default DayTimeline;
