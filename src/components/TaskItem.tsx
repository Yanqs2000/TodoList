import { useState, useCallback, useRef, useEffect } from 'react';
import type { Todo, Priority, TimeField } from '../types';
import { CATEGORY_LABELS } from '../constants';
import '../styles/TaskItem.css';
import '../styles/DragDrop.css';

const formatTimeTag = (time: TimeField): string => {
  const formatSingle = (iso: string): string => {
    if (!iso) return '';
    const [datePart, timePart] = iso.split('T');
    const [, month, day] = datePart.split('-');
    return `${month}/${day} ${timePart}`;
  };
  if (time.end) {
    return `${formatSingle(time.start)} - ${formatSingle(time.end)}`;
  }
  return formatSingle(time.start);
};

interface TaskItemProps {
  task: Todo;
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
  onEdit?: (id: string, updates: Partial<Pick<Todo, 'text' | 'priority' | 'time' | 'category' | 'notes'>>) => void;
  draggingId?: string | null;
  overId?: string | null;
  onDragStart?: (e: React.DragEvent, id: string) => void;
  onDragOver?: (e: React.DragEvent, id: string) => void;
  onDragLeave?: (e: React.DragEvent) => void;
  onDrop?: (e: React.DragEvent, id: string) => void;
  onDragEnd?: () => void;
}

const priorityLabels: Record<Priority, string> = {
  low: '低',
  medium: '中',
  high: '高',
};

function TaskItem({
  task, onToggle, onDelete, onEdit,
  draggingId, overId,
  onDragStart, onDragOver, onDragLeave, onDrop, onDragEnd,
}: TaskItemProps) {
  const [removing, setRemoving] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [editText, setEditText] = useState(task.text);
  const editInputRef = useRef<HTMLInputElement>(null);
  const removeTimerRef = useRef<number | null>(null);
  const removeDoneRef = useRef(false);
  const removeRef = useRef(onDelete);
  removeRef.current = onDelete;

  useEffect(() => {
    if (isEditing && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [isEditing]);

  useEffect(() => {
    return () => {
      if (removeTimerRef.current !== null) {
        clearTimeout(removeTimerRef.current);
      }
    };
  }, []);

  const handleEditSubmit = () => {
    if (editText.trim() && editText !== task.text) {
      onEdit?.(task.id, { text: editText.trim() });
    }
    setIsEditing(false);
  };

  const handleEditKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleEditSubmit();
    if (e.key === 'Escape') { setEditText(task.text); setIsEditing(false); }
  };

  const handleToggle = useCallback(() => {
    onToggle(task.id);
  }, [onToggle, task.id]);

  const handleDelete = useCallback(() => {
    if (!window.confirm(`确定要删除任务「${task.text}」吗？`)) return;
    removeDoneRef.current = false;
    setRemoving(true);
    const onEnd = () => {
      if (removeDoneRef.current) return;
      removeDoneRef.current = true;
      if (removeTimerRef.current !== null) {
        clearTimeout(removeTimerRef.current);
        removeTimerRef.current = null;
      }
      removeRef.current(task.id);
    };
    removeTimerRef.current = window.setTimeout(onEnd, 220);
    const el = document.querySelector(`[data-task-id="${task.id}"]`);
    if (el) {
      el.addEventListener('animationend', onEnd, { once: true });
    }
  }, [task.id, task.text]);

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
      <input
        type="checkbox"
        className="checkbox"
        checked={task.completed}
        onChange={handleToggle}
        aria-label={task.completed ? '标记为未完成' : '标记为已完成'}
      />
      <svg className="checkbox-mark" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M5 13l4 4L19 7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {isEditing ? (
        <input
          ref={editInputRef}
          className="edit-input"
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          onBlur={handleEditSubmit}
          onKeyDown={handleEditKeyDown}
        />
      ) : (
        <span className="task-text" onClick={() => setIsEditing(true)}>
          {task.text}
        </span>
      )}
      <span className={`priority-tag ${task.priority}`}>
        {priorityLabels[task.priority]}
      </span>
      {task.category && (
        <span className={`category-tag category-${task.category}`}>
          {CATEGORY_LABELS[task.category] || task.category}
        </span>
      )}
      {task.time && (
        <span className="time-tag">
          {formatTimeTag(task.time)}
        </span>
      )}
      <button
        className="btn-edit"
        aria-label="编辑任务"
        onClick={() => setIsEditing(true)}
      >
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Z" />
        </svg>
      </button>
      {task.notes && !isExpanded && (
        <span className="notes-indicator" title="有备注">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
          </svg>
        </span>
      )}
      {task.notes && (
        <button
          className={`btn-expand${isExpanded ? ' expanded' : ''}`}
          onClick={() => setIsExpanded(!isExpanded)}
          aria-label={isExpanded ? '收起备注' : '展开备注'}
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
          </svg>
        </button>
      )}
      <button
        className="btn-delete"
        aria-label="删除任务"
        onClick={handleDelete}
      >
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
      </button>
      {task.notes && isExpanded && (
        <div className="task-notes">
          <p>{task.notes}</p>
        </div>
      )}
    </div>
  );
}

export default TaskItem;
