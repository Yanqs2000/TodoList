import { useState, useRef, useEffect, useCallback } from 'react';
import type { TimeField, Category } from '../types';
import { CATEGORY_LABELS } from '../constants';
import TimePicker from './TimePicker';
import '../styles/TaskInput.css';

interface TaskInputProps {
  addTask: (text: string, time?: TimeField, category?: Category) => void;
}

function TaskInput({ addTask }: TaskInputProps) {
  const [value, setValue] = useState('');
  const [time, setTime] = useState<TimeField | undefined>();
  const [category, setCategory] = useState<Category>('other');
  const [showTimePicker, setShowTimePicker] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const isComposingRef = useRef(false);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = useCallback(() => {
    if (value.trim()) {
      addTask(value, time, category);
      setValue('');
      setTime(undefined);
      inputRef.current?.focus();
    }
  }, [value, time, category, addTask]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isComposingRef.current) {
      handleSubmit();
    }
  };

  const handleCompositionStart = () => {
    isComposingRef.current = true;
  };

  const handleCompositionEnd = () => {
    isComposingRef.current = false;
  };

  const handleTimeChange = (newTime: TimeField | undefined) => {
    setTime(newTime);
  };

  const formatTimeDisplay = (t: TimeField): string => {
    const formatSingle = (iso: string): string => {
      if (!iso) return '';
      const [datePart, timePart] = iso.split('T');
      const [, month, day] = datePart.split('-');
      return `${month}/${day} ${timePart}`;
    };
    if (t.end) {
      return `${formatSingle(t.start)} - ${formatSingle(t.end)}`;
    }
    return formatSingle(t.start);
  };

  return (
    <div className="input-area">
      <div className="input-row">
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onCompositionStart={handleCompositionStart}
          onCompositionEnd={handleCompositionEnd}
          placeholder="添加新任务..."
          autoComplete="off"
        />
        <div className="input-actions">
          {time && (
            <span className="time-preview">{formatTimeDisplay(time)}</span>
          )}
          <button
            className={`icon-btn time-btn${time ? ' has-time' : ''}`}
            onClick={() => setShowTimePicker(!showTimePicker)}
            aria-label="设置时间"
            title="设置时间"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
          </button>
          {showTimePicker && (
            <TimePicker
              time={time}
              onTimeChange={handleTimeChange}
              onClose={() => setShowTimePicker(false)}
            />
          )}
        </div>
        <button className="btn-add" onClick={handleSubmit}>
          添加
        </button>
      </div>
      <div className="category-row">
        {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
          <button
            key={key}
            className={`category-btn${category === key ? ' active' : ''}`}
            onClick={() => setCategory(key as Category)}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

export default TaskInput;
