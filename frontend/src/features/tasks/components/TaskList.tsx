import { useState, useEffect } from 'react';
import type { Todo, FilterType } from '@/shared/types';
import { useDragDrop } from '../hooks/useDragDrop';
import { proximityOf, type Proximity } from '../lib/timeProximity';
import '../styles/TaskList.css';
import TaskItem from './TaskItem';
import EmptyState from './EmptyState';
import DayTimeline from './DayTimeline';

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
  pendingTaskIds?: ReadonlySet<string>;
  reorderPending?: boolean;
  reorderDisabled?: boolean;
  selectedTaskId?: string | null;
  onSelectTask?: (id: string | null) => void;
  /** Override "now" for testing; live Date.now() when omitted. */
  now?: number;
}

interface TaskGroup {
  key: string;
  label: string;
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
  return [
    { key: 'overdue', label: '已过期', items: buckets.overdue },
    { key: 'today', label: '今天', items: buckets.today },
    { key: 'future', label: '以后', items: buckets.future },
    { key: 'unscheduled', label: '待安排', items: buckets.unscheduled },
  ].filter(g => g.items.length > 0);
}

function TaskList({ tasks, filter, hasAnyTasks, sortMode, onToggleSortMode, onToggle, onDelete, onEdit, onReorder, pendingTaskIds = new Set(), reorderPending = false, reorderDisabled = false, selectedTaskId, onSelectTask, now: nowProp }: TaskListProps) {
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

  const renderItem = (task: Todo) => (
    <TaskItem
      key={task.id}
      task={task}
      selected={selectedTaskId === task.id}
      proximity={proximityFor(task)}
      onToggle={onToggle}
      onDelete={onDelete}
      onEdit={onEdit}
      pending={pendingTaskIds.has(task.id) || reorderPending}
      onSelect={onSelectTask}
      draggingId={drag.draggingId}
      overId={drag.overId}
      onDragStart={!reorderDisabled && !reorderPending && pendingTaskIds.size === 0 ? drag.handleDragStart : undefined}
      onDragOver={!reorderDisabled && !reorderPending && pendingTaskIds.size === 0 ? drag.handleDragOver : undefined}
      onDragLeave={!reorderDisabled && !reorderPending && pendingTaskIds.size === 0 ? drag.handleDragLeave : undefined}
      onDrop={!reorderDisabled && !reorderPending && pendingTaskIds.size === 0 ? drag.handleDrop : undefined}
      onDragEnd={!reorderDisabled && !reorderPending && pendingTaskIds.size === 0 ? drag.handleDragEnd : undefined}
    />
  );

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
          手动排序
        </button>
        <button
          className={`sort-btn${sortMode === 'time' ? ' active' : ''}`}
          onClick={() => onToggleSortMode('time')}
          aria-pressed={sortMode === 'time'}
        >
          按时间排序
        </button>
      </div>
      {grouped ? (
        grouped.map(group => (
          <div key={group.key} className="task-group" role="group" aria-label={group.label}>
            <div className="task-group__header">
              <span className={`task-group__dot task-group__dot--${group.key}`} aria-hidden="true" />
              <span className="task-group__label">{group.label}</span>
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
