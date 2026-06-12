import { useState, useRef, useEffect } from 'react';
import type { TimeField } from '../types';
import '../styles/TimePicker.css';

interface TimePickerProps {
  time?: TimeField;
  onTimeChange: (time: TimeField | undefined) => void;
  onClose: () => void;
}

function TimePicker({ time, onTimeChange, onClose }: TimePickerProps) {
  const [mode, setMode] = useState<'point' | 'range'>(time?.end ? 'range' : 'point');
  const [start, setStart] = useState(time?.start || '');
  const [end, setEnd] = useState(time?.end || '');
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  const handleConfirm = () => {
    if (start) {
      onTimeChange({ start, end: mode === 'range' ? end : undefined });
    }
    onClose();
  };

  const handleClear = () => {
    onTimeChange(undefined);
    onClose();
  };

  return (
    <div className="time-picker" ref={ref}>
      <div className="time-picker-header">
        <button
          className={`time-mode-btn${mode === 'point' ? ' active' : ''}`}
          onClick={() => setMode('point')}
        >
          时间点
        </button>
        <button
          className={`time-mode-btn${mode === 'range' ? ' active' : ''}`}
          onClick={() => setMode('range')}
        >
          时间段
        </button>
      </div>

      <div className="time-picker-body">
        <div className="time-input-group">
          <label>开始</label>
          <input
            type="time"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </div>

        {mode === 'range' && (
          <div className="time-input-group">
            <label>结束</label>
            <input
              type="time"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
          </div>
        )}
      </div>

      <div className="time-picker-footer">
        <button className="time-btn-clear" onClick={handleClear}>
          清除
        </button>
        <button className="time-btn-confirm" onClick={handleConfirm} disabled={!start}>
          确认
        </button>
      </div>
    </div>
  );
}

export default TimePicker;