import { useState, useRef, useEffect, useCallback } from 'react';
import type { TimeField } from '../types';
import TimePicker from './TimePicker';
import '../styles/TaskInput.css';

interface TaskInputProps {
  addTask: (text: string, time?: TimeField) => void;
}

function TaskInput({ addTask }: TaskInputProps) {
  const [value, setValue] = useState('');
  const [time, setTime] = useState<TimeField | undefined>();
  const [showTimePicker, setShowTimePicker] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const isComposingRef = useRef(false);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = useCallback(() => {
    if (value.trim()) {
      addTask(value, time);
      setValue('');
      setTime(undefined);
      inputRef.current?.focus();
    }
  }, [value, time, addTask]);

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
    if (t.end) {
      return `${t.start}-${t.end}`;
    }
    return t.start;
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
    </div>
  );
}

export default TaskInput;
