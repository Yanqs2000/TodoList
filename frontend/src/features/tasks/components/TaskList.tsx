import { useState, useEffect } from 'react';
import type { Todo, FilterType } from '@/shared/types';
import type { TaskMutationKind } from '../hooks/useTodos';
import { useDragDrop } from '../hooks/useDragDrop';
import { proximityOf, type Proximity } from '../lib/timeProximity';
import '../styles/TaskList.css';
import TaskItem from './TaskItem';
import EmptyState from './EmptyState';
import DayTimeline from './DayTimeline';
import { useI18n } from '@/features/i18n/I18nProvider';
import type { TranslationKey } from '@/features/i18n/translations';

interface TaskListProps {
  tasks: Todo[];
  filter: FilterType;
  hasAnyTasks: boolean;
  sortMode: 'manual' | 'time';
  onToggleSortMode: (mode: 'manual' | 'time') => void;
  onToggle: (id: string) => Promise<unknown> | void;
  onDelete: (id: string) => Promise<boolean> | void;
  onEdit?: (id: string, updates: Partial<Pick<Todo, 'text' | 'priority' | 'time' | 'category' | 'notes'>>) => Promise<boolean> | void;
  onReorder: (fromId: string, toId: string) => Promise<boolean> | void;
  pendingMutations?: ReadonlyMap<string, ReadonlySet<TaskMutationKind>>;
  reorderPending?: boolean;
  reorderDisabled?: boolean;
  selectedTaskId?: string | null;
  onSelectTask?: (id: string | null) => void;
  /** Override "now" for testing; live Date.now() when omitted. */
  now?: number;
}

interface TaskGroup {
  key: string;
  label: TranslationKey;
  items: Todo[];
}

// Buckets for the active + time-sorted view, in display order.
function groupByProximity(tasks: Todo[], now: number): TaskGroup[] {
  const buckets: Record<string, Todo[]> = { overdue: [], today: [], future: [], unscheduled: [] };
  for (const t of tasks) {
    const p = proximityOf(t.time, now);
    if (p === 'overdue') buckets.overdue.push(t);
    else if (p === 'soon' || p === 'today') buckets.today.push(t);
    else if (p === 'future') buckets.future.push(t);
    else buckets.unscheduled.push(t);
  }
  const groups: TaskGroup[] = [
    { key: 'overdue', label: 'group.overdue', items: buckets.overdue },
    { key: 'today', label: 'group.today', items: buckets.today },
    { key: 'future', label: 'group.future', items: buckets.future },
    { key: 'unscheduled', label: 'group.unscheduled', items: buckets.unscheduled },
  ];
  return groups.filter(g => g.items.length > 0);
}

function TaskList({ tasks, filter, hasAnyTasks, sortMode, onToggleSortMode, onToggle, onDelete, onEdit, onReorder, pendingMutations = new Map(), reorderPending = false, reorderDisabled = false, selectedTaskId, onSelectTask, now: nowProp }: TaskListProps) {
  const { t } = useI18n();
  const drag = useDragDrop(onReorder);
  const [nowState, setNowState] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNowState(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, []);
  const now = nowProp ?? nowState;

  if (tasks.length === 0) {
    return <EmptyState filter={filter} hasAnyTasks={hasAnyTasks} />;
  }

  const isActive = filter === 'active';
  const grouped = isActive && sortMode === 'time' ? groupByProximity(tasks, now) : null;
  const proximityFor = (t: Todo): Proximity | undefined => (isActive ? proximityOf(t.time, now) : undefined);

  const collectionMutationPending = [...pendingMutations.values()].some(mutations => (
    mutations.has('delete') || mutations.has('clear')
  ));
  const dragDisabled = reorderDisabled || reorderPending || collectionMutationPending;

  const renderItem = (task: Todo) => {
    const mutations = pendingMutations.get(task.id);
    const exclusive = mutations?.has('delete') || mutations?.has('clear');
    return <TaskItem
      key={task.id}
      task={task}
      selected={selectedTaskId === task.id}
      proximity={proximityFor(task)}
      onToggle={onToggle}
      onDelete={onDelete}
      onEdit={onEdit}
      togglePending={exclusive || mutations?.has('toggle')}
      editPending={exclusive || mutations?.has('edit')}
      deletePending={Boolean(mutations?.size) || reorderPending}
      onSelect={onSelectTask}
      draggingId={drag.draggingId}
      overId={drag.overId}
      onDragStart={!dragDisabled ? drag.handleDragStart : undefined}
      onDragOver={!dragDisabled ? drag.handleDragOver : undefined}
      onDragLeave={!dragDisabled ? drag.handleDragLeave : undefined}
      onDrop={!dragDisabled ? drag.handleDrop : undefined}
      onDragEnd={!dragDisabled ? drag.handleDragEnd : undefined}
    />
  };

  return (
    <div className="task-list">
      {isActive && (
        <DayTimeline tasks={tasks} selectedTaskId={selectedTaskId} onSelectTask={onSelectTask} now={now} />
      )}
      <div className="sort-bar">
        <button
          className={`sort-btn${sortMode === 'manual' ? ' active' : ''}`}
          onClick={() => onToggleSortMode('manual')}
          aria-pressed={sortMode === 'manual'}
        >
          {t('sort.manual')}
        </button>
        <button
          className={`sort-btn${sortMode === 'time' ? ' active' : ''}`}
          onClick={() => onToggleSortMode('time')}
          aria-pressed={sortMode === 'time'}
        >
          {t('sort.time')}
        </button>
      </div>
      {grouped ? (
        grouped.map(group => (
          <div key={group.key} className="task-group" role="group" aria-label={t(group.label)}>
            <div className="task-group__header">
              <span className={`task-group__dot task-group__dot--${group.key}`} aria-hidden="true" />
              <span className="task-group__label">{t(group.label)}</span>
              <span className="task-group__count">{group.items.length}</span>
            </div>
            {group.items.map(renderItem)}
          </div>
        ))
      ) : (
        tasks.map(renderItem)
      )}
    </div>
  );
}

export default TaskList;
