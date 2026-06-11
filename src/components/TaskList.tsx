import type { Todo, FilterType } from '../types';
import { useDragDrop } from '../hooks/useDragDrop';
import '../styles/TaskList.css';
import TaskItem from './TaskItem';
import EmptyState from './EmptyState';

interface TaskListProps {
  tasks: Todo[];
  filter: FilterType;
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
  onReorder: (fromId: string, toId: string) => void;
}

function TaskList({ tasks, filter, onToggle, onDelete, onReorder }: TaskListProps) {
  const drag = useDragDrop(onReorder);

  if (tasks.length === 0) {
    return <EmptyState filter={filter} />;
  }

  return (
    <div className="task-list">
      {tasks.map(task => (
        <TaskItem
          key={task.id}
          task={task}
          onToggle={onToggle}
          onDelete={onDelete}
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
