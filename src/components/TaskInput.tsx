import { useState, useRef, useEffect, useCallback } from 'react';
import '../styles/TaskInput.css';

interface TaskInputProps {
  addTask: (text: string) => void;
}

function TaskInput({ addTask }: TaskInputProps) {
  const [value, setValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const isComposingRef = useRef(false);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = useCallback(() => {
    if (value.trim()) {
      addTask(value);
      setValue('');
      inputRef.current?.focus();
    }
  }, [value, addTask]);

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

  return (
    <div className="input-area">
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
      <button className="btn-add" onClick={handleSubmit}>
        添加
      </button>
    </div>
  );
}

export default TaskInput;
