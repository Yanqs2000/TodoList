import { useState, useCallback, useRef } from 'react';
import type { Todo, Priority } from '../types';
import { escapeHtml } from '../utils/escapeHtml';
import '../styles/TaskItem.css';
import '../styles/DragDrop.css';

interface TaskItemProps {
  task: Todo;
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
  draggingId?: string | null;
  overId?: string | null;
  onDragStart?: (e: React.DragEvent, id: string) => void;
  onDragOver?: (e: React.DragEvent, id: string) => void;
  onDragLeave?: () => void;
  onDrop?: (e: React.DragEvent, id: string) => void;
  onDragEnd?: () => void;
}

const priorityLabels: Record<Priority, string> = {
  low: '低',
  medium: '中',
  high: '高',
};

function TaskItem({
  task, onToggle, onDelete,
  draggingId, overId,
  onDragStart, onDragOver, onDragLeave, onDrop, onDragEnd,
}: TaskItemProps) {
  const [removing, setRemoving] = useState(false);
  const removeRef = useRef(onDelete);
  removeRef.current = onDelete;

  const handleToggle = useCallback(() => {
    onToggle(task.id);
  }, [onToggle, task.id]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onToggle(task.id);
    }
  };

  const handleDelete = useCallback(() => {
    setRemoving(true);
    const onEnd = () => {
      removeRef.current(task.id);
    };
    const el = document.querySelector(`[data-task-id="${task.id}"]`);
    if (el) {
      el.addEventListener('animationend', onEnd, { once: true });
      setTimeout(onEnd, 200);
    } else {
      removeRef.current(task.id);
    }
  }, [task.id]);

  const isDragging = draggingId === task.id;
  const isOver = overId === task.id && draggingId !== task.id;

  return (
    <div
      className={`task-item${task.completed ? ' completed' : ''}${removing ? ' removing' : ''}${isDragging ? ' dragging' : ''}${isOver ? ' drag-over' : ''}`}
      data-task-id={task.id}
      draggable={!!onDragStart}
      onDragStart={onDragStart ? (e) => onDragStart(e, task.id) : undefined}
      onDragOver={onDragOver ? (e) => onDragOver(e, task.id) : undefined}
      onDragLeave={onDragLeave}
      onDrop={onDrop ? (e) => onDrop(e, task.id) : undefined}
      onDragEnd={onDragEnd}
    >
      <div
        className="checkbox"
        role="checkbox"
        aria-checked={task.completed}
        tabIndex={0}
        onClick={handleToggle}
        onKeyDown={handleKeyDown}
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
          <path
            d="M5 13l4 4L19 7"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
      <span className="task-text">{escapeHtml(task.text)}</span>
      <span className={`priority-tag ${task.priority}`}>
        {priorityLabels[task.priority]}
      </span>
      <button
        className="btn-delete"
        aria-label="删除任务"
        onClick={handleDelete}
      >
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2}>
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
      </button>
    </div>
  );
}

export default TaskItem;
