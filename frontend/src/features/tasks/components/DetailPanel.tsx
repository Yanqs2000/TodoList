import { useState, useEffect, useRef } from 'react';
import type { Todo, Category, TimeField } from '@/shared/types';
import type { TaskMutationKind } from '../hooks/useTodos';
import { CATEGORY_LABELS, PRIORITY_LABELS, PRIORITIES } from '@/shared/constants';
import { useConfirm } from '@/shared/components/ConfirmDialog';
import { formatTimeField } from '../lib/formatTime';
import TimePicker from './TimePicker';
import '../styles/DetailPanel.css';

interface DetailPanelProps {
  selectedTask: Todo | null;
  onEdit: (id: string, updates: Partial<Pick<Todo, 'text' | 'priority' | 'time' | 'category' | 'notes'>>) => Promise<boolean> | void;
  onToggle: (id: string) => Promise<unknown> | void;
  onDelete: (id: string) => Promise<boolean> | void;
  pendingMutations?: ReadonlySet<TaskMutationKind>;
  deleteBlocked?: boolean;
  onClose: () => void;
  stats: { total: number; active: number; completed: number };
  todayCompleted: number;
  dailyGoal: number;
  streakDays: number;
}

const priorityOptions = PRIORITIES.map(p => ({ value: p, label: PRIORITY_LABELS[p] }));

const categoryOptions: Category[] = ['work', 'study', 'life', 'other'];

const formatTimeTag = formatTimeField;

function DetailPanel({
  selectedTask,
  onEdit,
  onToggle,
  onDelete,
  pendingMutations,
  deleteBlocked = false,
  onClose,
  stats,
  todayCompleted,
  dailyGoal,
  streakDays,
}: DetailPanelProps) {
  const exclusivePending = pendingMutations?.has('delete') || pendingMutations?.has('clear');
  const editPending = Boolean(exclusivePending || pendingMutations?.has('edit'));
  const togglePending = Boolean(exclusivePending || pendingMutations?.has('toggle'));
  const deletePending = deleteBlocked || Boolean(pendingMutations?.size);
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editTitle, setEditTitle] = useState(selectedTask?.text ?? '');
  const [notesDraft, setNotesDraft] = useState(selectedTask?.notes ?? '');
  const [showTimePicker, setShowTimePicker] = useState(false);
  const confirm = useConfirm();
  const titleInputRef = useRef<HTMLInputElement>(null);
  const notesRef = useRef<HTMLTextAreaElement>(null);

  // Reset internal edit state when the selected task changes.
  useEffect(() => {
    setIsEditingTitle(false);
    setEditTitle(selectedTask?.text ?? '');
    setNotesDraft(selectedTask?.notes ?? '');
    setShowTimePicker(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTask?.id]);

  // Auto-focus and select the title input when entering edit mode.
  useEffect(() => {
    if (isEditingTitle && titleInputRef.current) {
      titleInputRef.current.focus();
      titleInputRef.current.select();
    }
  }, [isEditingTitle]);

  // Auto-grow the notes textarea to fit its content.
  useEffect(() => {
    const el = notesRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [notesDraft]);

  const startEditTitle = () => {
    setEditTitle(selectedTask?.text ?? '');
    setIsEditingTitle(true);
  };

  const submitTitle = () => {
    if (!selectedTask) {
      setIsEditingTitle(false);
      return;
    }
    const trimmed = editTitle.trim();
    if (trimmed && trimmed !== selectedTask.text) {
      void onEdit(selectedTask.id, { text: trimmed });
    }
    setIsEditingTitle(false);
  };

  const cancelTitle = () => {
    setEditTitle(selectedTask?.text ?? '');
    setIsEditingTitle(false);
  };

  const handleTitleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      submitTitle();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      cancelTitle();
    }
  };

  const handleNotesBlur = () => {
    if (!selectedTask) return;
    const original = selectedTask.notes ?? '';
    if (notesDraft !== original) {
      void onEdit(selectedTask.id, { notes: notesDraft || undefined });
    }
  };

  const handleClearTime = () => {
    if (!selectedTask) return;
    void onEdit(selectedTask.id, { time: undefined });
    setShowTimePicker(false);
  };

  const handleTimeChange = (time: TimeField | undefined) => {
    if (!selectedTask) return;
    void onEdit(selectedTask.id, { time });
  };

  const handleDelete = async () => {
    if (!selectedTask) return;
    const ok = await confirm({
      title: '删除任务',
      message: `确定要删除任务「${selectedTask.text}」吗？`,
      confirmText: '删除',
      danger: true,
    });
    if (ok) {
      await onDelete(selectedTask.id);
    }
  };

  const handleStatusToggle = () => {
    if (!selectedTask) return;
    void onToggle(selectedTask.id);
  };

  const CloseIcon = (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );

  // State A: today summary (no task selected)
  if (!selectedTask) {
    return (
      <aside className="detail">
        <header className="detail__header">
          <div className="detail__heading">
            <h2 className="detail__title">今日摘要</h2>
            <p className="detail__subtitle">未选中任务</p>
          </div>
          <button
            className="detail__close"
            onClick={onClose}
            aria-label="关闭详情面板"
          >
            {CloseIcon}
          </button>
        </header>

        <div className="detail__summary">
          <div className="detail__summary-card">
            <div className="detail__summary-label">今日完成</div>
            <div className="detail__summary-value">{todayCompleted}</div>
            <div className="detail__summary-sub">目标 {dailyGoal}</div>
          </div>
          <div className="detail__summary-card">
            <div className="detail__summary-label">连续天数</div>
            <div className="detail__summary-value">{streakDays}</div>
          </div>
          <div className="detail__summary-card">
            <div className="detail__summary-label">总任务</div>
            <div className="detail__summary-value">{stats.total}</div>
            <div className="detail__summary-sub">进行中 {stats.active}</div>
          </div>
        </div>

        <p className="detail__hint">点击左侧任务查看详情，或按 ⌘N 创建新任务</p>
      </aside>
    );
  }

  // State B: task detail
  return (
    <aside className="detail">
      <header className="detail__header">
        <div className="detail__title-area">
          {isEditingTitle ? (
            <input
              ref={titleInputRef}
              type="text"
              className="detail__title-input"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              onBlur={submitTitle}
              onKeyDown={handleTitleKeyDown}
              aria-label="编辑任务标题"
              disabled={editPending}
            />
          ) : (
            <h2
              className="detail__title detail__title--editable"
              onClick={startEditTitle}
              title="点击编辑标题"
            >
              {selectedTask.text}
            </h2>
          )}
        </div>
        <button
          className="detail__close"
          onClick={onClose}
          aria-label="关闭详情面板"
        >
          {CloseIcon}
        </button>
      </header>

      <button
        className={`detail__status${selectedTask.completed ? ' detail__status--done' : ''}`}
        onClick={handleStatusToggle}
        aria-label={selectedTask.completed ? '标记为未完成' : '标记为已完成'}
        disabled={togglePending}
      >
        {selectedTask.completed && (
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        )}
        {selectedTask.completed ? '已完成' : '未完成'}
      </button>

      <div className="detail__body">
        <section className="detail__section">
          <div className="detail__label">优先级</div>
          <div className="detail__btn-group">
            {priorityOptions.map((opt) => (
              <button
                key={opt.value}
                className={`detail__btn${selectedTask.priority === opt.value ? ' detail__btn--active' : ''}`}
                data-priority={opt.value}
                onClick={() => onEdit(selectedTask.id, { priority: opt.value })}
                disabled={editPending}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </section>

        <section className="detail__section">
          <div className="detail__label">分类</div>
          <div className="detail__btn-group">
            {categoryOptions.map((cat) => (
              <button
                key={cat}
                className={`detail__btn${selectedTask.category === cat ? ' detail__btn--active' : ''}`}
                onClick={() => onEdit(selectedTask.id, { category: cat })}
                disabled={editPending}
              >
                {CATEGORY_LABELS[cat]}
              </button>
            ))}
          </div>
        </section>

        <section className="detail__section">
          <div className="detail__label">时间</div>
          <div className="detail__field">
            {selectedTask.time ? (
              <div className="detail__time-tag">
                <svg className="detail__time-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6l4 2m6-2a10 10 0 11-20 0 10 10 0 0120 0z" />
                </svg>
                <span>{formatTimeTag(selectedTask.time)}</span>
                <button
                  className="detail__time-clear"
                  onClick={handleClearTime}
                  aria-label="清除时间"
                  disabled={editPending}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ) : (
              <span className="detail__time-empty">未设置</span>
            )}
            <button
              type="button"
              className="detail__btn detail__time-edit"
              onClick={() => setShowTimePicker((s) => !s)}
              aria-expanded={showTimePicker}
              disabled={editPending}
            >
              {showTimePicker ? '收起' : selectedTask.time ? '修改时间' : '设置时间'}
            </button>
          </div>
          {showTimePicker && (
            <div className="detail__time-picker-wrap">
              <TimePicker
                time={selectedTask.time}
                onTimeChange={handleTimeChange}
                onClose={() => setShowTimePicker(false)}
              />
            </div>
          )}
        </section>

        <section className="detail__section">
          <div className="detail__label">备注</div>
          <textarea
            ref={notesRef}
            className="detail__notes"
            value={notesDraft}
            onChange={(e) => setNotesDraft(e.target.value)}
            onBlur={handleNotesBlur}
            placeholder="添加备注…"
            disabled={editPending}
          />
        </section>
      </div>

      <div className="detail__footer">
        <button
          className="detail__delete"
          onClick={handleDelete}
          disabled={deletePending}
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
          删除任务
        </button>
      </div>
    </aside>
  );
}

export default DetailPanel;
