import type { Todo, FilterType } from '@/shared/types';
import { useDragDrop } from '../hooks/useDragDrop';
import '../styles/TaskList.css';
import TaskItem from './TaskItem';
import EmptyState from './EmptyState';

interface TaskListProps {
  tasks: Todo[];
  filter: FilterType;
  sortMode: 'manual' | 'time';
  onToggleSortMode: (mode: 'manual' | 'time') => void;
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
  onEdit?: (id: string, updates: Partial<Pick<Todo, 'text' | 'priority' | 'time' | 'category' | 'notes'>>) => void;
  onReorder: (fromId: string, toId: string) => void;
}

function TaskList({ tasks, filter, sortMode, onToggleSortMode, onToggle, onDelete, onEdit, onReorder }: TaskListProps) {
  const drag = useDragDrop(onReorder);

  if (tasks.length === 0) {
    return <EmptyState filter={filter} />;
  }

  return (
    <div className="task-list">
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
      {tasks.map(task => (
        <TaskItem
          key={task.id}
          task={task}
          onToggle={onToggle}
          onDelete={onDelete}
          onEdit={onEdit}
          draggingId={drag.draggingId}
          overId={drag.overId}
          onDragStart={drag.handleDragStart}
          onDragOver={drag.handleDragOver}
          onDragLeave={drag.handleDragLeave}
          onDrop={drag.handleDrop}
          onDragEnd={drag.handleDragEnd}
        />
      ))}
    </div>
  );
}

export default TaskList;
