import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import type { TimeField, Category, Priority } from '@/shared/types';
import { CATEGORY_LABELS, PRIORITY_LABELS, PRIORITIES } from '@/shared/constants';
import { formatTimeField } from '../lib/formatTime';
import TimePicker from './TimePicker';
import '../styles/CreateTaskModal.css';

interface CreateTaskModalProps {
  open: boolean;
  onClose: () => void;
  onAdd: (text: string, time?: TimeField, category?: Category, priority?: Priority, notes?: string) => void;
  defaultPriority: Priority;
}

const priorityOptions = PRIORITIES.map(p => ({ value: p, label: PRIORITY_LABELS[p] }));

function formatTimeDisplay(t: TimeField): string {
  return formatTimeField(t);
}

function CreateTaskModal({ open, onClose, onAdd, defaultPriority }: CreateTaskModalProps) {
  const [text, setText] = useState('');
  const [priority, setPriority] = useState<Priority>(defaultPriority);
  const [category, setCategory] = useState<Category>('other');
  const [time, setTime] = useState<TimeField | undefined>(undefined);
  const [notes, setNotes] = useState('');
  const [showTimePicker, setShowTimePicker] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const isComposingRef = useRef(false);

  // Refs holding latest values for the document-level keydown handler so the
  // listener does not need to be re-subscribed on every keystroke.
  const textRef = useRef(text);
  textRef.current = text;
  const timeRef = useRef(time);
  timeRef.current = time;
  const categoryRef = useRef(category);
  categoryRef.current = category;
  const priorityRef = useRef(priority);
  priorityRef.current = priority;
  const notesRef = useRef(notes);
  notesRef.current = notes;
  const showTimePickerRef = useRef(showTimePicker);
  showTimePickerRef.current = showTimePicker;
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const onAddRef = useRef(onAdd);
  onAddRef.current = onAdd;
  const defaultPriorityRef = useRef(defaultPriority);
  defaultPriorityRef.current = defaultPriority;

  const submit = (): void => {
    const trimmed = textRef.current.trim();
    if (!trimmed) return;
    onAddRef.current(trimmed, timeRef.current, categoryRef.current, priorityRef.current, notesRef.current);
    setText('');
    setPriority(defaultPriorityRef.current);
    setCategory('other');
    setTime(undefined);
    setNotes('');
    setShowTimePicker(false);
    onCloseRef.current();
  };

  const submitRef = useRef(submit);
  submitRef.current = submit;

  // Reset internal state and autofocus the input every time the modal opens.
  // Only re-runs on `open` transitions; defaultPriorityRef holds the latest
  // value so we don't wipe in-progress input if the parent updates the default
  // while the modal is open.
  useEffect(() => {
    if (!open) return;
    setText('');
    setPriority(defaultPriorityRef.current);
    setCategory('other');
    setTime(undefined);
    setNotes('');
    setShowTimePicker(false);
    const id = window.requestAnimationFrame(() => {
      const el = inputRef.current;
      if (!el) return;
      el.focus();
      el.select();
    });
    return () => window.cancelAnimationFrame(id);
  }, [open]);

  // Esc closes (defer to TimePicker when it is open); Cmd/Ctrl+Enter submits.
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (showTimePickerRef.current) return;
        e.preventDefault();
        onCloseRef.current();
        return;
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        if (isComposingRef.current) return;
        e.preventDefault();
        submitRef.current();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open]);

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    // Plain Enter submits from the input. Cmd/Ctrl+Enter is handled by the
    // document-level listener so we deliberately skip it here to avoid
    // double-submitting (state updates are async, so textRef would still hold
    // the old value when the second handler fires).
    if (e.key === 'Enter' && !e.metaKey && !e.ctrlKey && !isComposingRef.current) {
      e.preventDefault();
      submit();
    }
  };

  const handleCompositionStart = () => {
    isComposingRef.current = true;
  };
  const handleCompositionEnd = () => {
    isComposingRef.current = false;
  };

  const handleOverlayMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose();
  };

  if (!open) return null;

  return createPortal(
    <div className="create-modal__overlay" onMouseDown={handleOverlayMouseDown}>
      <div
        className="create-modal__card"
        role="dialog"
        aria-modal="true"
        aria-label="新建任务"
      >
        <header className="create-modal__header">
          <h2 className="create-modal__title">新建任务</h2>
          <button
            type="button"
            className="create-modal__close"
            onClick={onClose}
            aria-label="关闭"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </header>

        <div className="create-modal__body">
          <div className="create-modal__field">
            <input
              ref={inputRef}
              type="text"
              className="create-modal__input"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleInputKeyDown}
              onCompositionStart={handleCompositionStart}
              onCompositionEnd={handleCompositionEnd}
              placeholder="今天要做什么？"
              autoComplete="off"
            />
          </div>

          <div className="create-modal__field">
            <span className="create-modal__label">优先级</span>
            <div className="create-modal__btn-group">
              {priorityOptions.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  className={`create-modal__btn${priority === opt.value ? ' create-modal__btn--active' : ''}`}
                  data-priority={opt.value}
                  onClick={() => setPriority(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div className="create-modal__field">
            <span className="create-modal__label">分类</span>
            <div className="create-modal__btn-group">
              {(Object.entries(CATEGORY_LABELS) as [Category, string][]).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  className={`create-modal__btn${category === key ? ' create-modal__btn--active' : ''}`}
                  data-category={key}
                  onClick={() => setCategory(key)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="create-modal__field">
            <span className="create-modal__label">时间</span>
            <div className="create-modal__time-row">
              <span className="create-modal__time-preview">
                {time ? formatTimeDisplay(time) : '未设置时间'}
              </span>
              <div className="create-modal__btn-group">
                <button
                  type="button"
                  className="create-modal__btn create-modal__btn--ghost"
                  onClick={() => setShowTimePicker((s) => !s)}
                  aria-expanded={showTimePicker}
                >
                  {showTimePicker ? '收起' : '设置时间'}
                </button>
                <button
                  type="button"
                  className="create-modal__btn create-modal__btn--ghost"
                  onClick={() => setTime(undefined)}
                  disabled={!time}
                >
                  清除时间
                </button>
              </div>
            </div>
            {showTimePicker && (
              <div className="create-modal__time-picker-wrap">
                <TimePicker
                  time={time}
                  onTimeChange={(t) => setTime(t)}
                  onClose={() => setShowTimePicker(false)}
                />
              </div>
            )}
          </div>

          <div className="create-modal__field">
            <span className="create-modal__label">备注</span>
            <textarea
              className="create-modal__textarea"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              onCompositionStart={handleCompositionStart}
              onCompositionEnd={handleCompositionEnd}
              placeholder="添加备注（可选）"
            />
          </div>
        </div>

        <footer className="create-modal__footer">
          <button type="button" className="create-modal__cancel" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="create-modal__submit"
            onClick={submit}
            disabled={!text.trim()}
          >
            创建任务
          </button>
        </footer>
      </div>
    </div>,
    document.body,
  );
}

export default CreateTaskModal;
