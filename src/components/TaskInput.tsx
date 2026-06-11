import { useState, useRef, useEffect } from 'react';
import '../styles/TaskInput.css';

interface TaskInputProps {
  addTask: (text: string) => void;
}

function TaskInput({ addTask }: TaskInputProps) {
  const [value, setValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = () => {
    if (value.trim()) {
      addTask(value);
      setValue('');
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSubmit();
    }
  };

  return (
    <div className="input-area">
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
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
