import { useState, useRef, useEffect } from 'react';
import type { TimeField } from '../types';
import '../styles/TimePicker.css';

interface TimePickerProps {
  time?: TimeField;
  onTimeChange: (time: TimeField | undefined) => void;
  onClose: () => void;
}

function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

function getFirstDayOfMonth(year: number, month: number): number {
  return new Date(year, month, 1).getDay();
}

function formatDate(year: number, month: number, day: number, time: string): string {
  const m = String(month + 1).padStart(2, '0');
  const d = String(day).padStart(2, '0');
  return `${year}-${m}-${d}T${time}`;
}

function parseDateTime(iso: string): { year: number; month: number; day: number; time: string } {
  if (!iso) return { year: new Date().getFullYear(), month: new Date().getMonth(), day: new Date().getDate(), time: '09:00' };
  const [datePart, timePart] = iso.split('T');
  const [year, month, day] = datePart.split('-').map(Number);
  return { year, month: month - 1, day, time: timePart || '09:00' };
}

function TimePicker({ time, onTimeChange, onClose }: TimePickerProps) {
  const [mode, setMode] = useState<'point' | 'range'>(time?.end ? 'range' : 'point');
  const startParsed = parseDateTime(time?.start || '');
  const endParsed = parseDateTime(time?.end || '');

  const [startDate, setStartDate] = useState(startParsed);
  const [endDate, setEndDate] = useState(endParsed);
  const [startTime, setStartTime] = useState(startParsed.time);
  const [endTime, setEndTime] = useState(endParsed.time);
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

  const handleDateSelect = (day: number, isEnd: boolean = false) => {
    const target = isEnd ? endDate : startDate;
    const setter = isEnd ? setEndDate : setStartDate;
    setter({ ...target, day });
  };

  const handleMonthChange = (delta: number, isEnd: boolean = false) => {
    const target = isEnd ? endDate : startDate;
    const setter = isEnd ? setEndDate : setStartDate;
    let newMonth = target.month + delta;
    let newYear = target.year;
    if (newMonth < 0) { newMonth = 11; newYear--; }
    if (newMonth > 11) { newMonth = 0; newYear++; }
    const maxDay = getDaysInMonth(newYear, newMonth);
    const newDay = Math.min(target.day, maxDay);
    setter({ year: newYear, month: newMonth, day: newDay, time: target.time });
  };

  const handleConfirm = () => {
    const start = formatDate(startDate.year, startDate.month, startDate.day, startTime);
    const end = mode === 'range'
      ? formatDate(endDate.year, endDate.month, endDate.day, endTime)
      : undefined;
    onTimeChange({ start, end });
    onClose();
  };

  const handleClear = () => {
    onTimeChange(undefined);
    onClose();
  };

  const renderCalendar = (date: typeof startDate, onDayClick: (day: number) => void, onMonthChange: (delta: number) => void) => {
    const daysInMonth = getDaysInMonth(date.year, date.month);
    const firstDay = getFirstDayOfMonth(date.year, date.month);
    const today = new Date();
    const isToday = (day: number) =>
      date.year === today.getFullYear() && date.month === today.getMonth() && day === today.getDate();
    const isSelected = (day: number) => day === date.day;

    const weekDays = ['日', '一', '二', '三', '四', '五', '六'];
    const monthNames = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];

    const days: (number | null)[] = [];
    for (let i = 0; i < firstDay; i++) days.push(null);
    for (let i = 1; i <= daysInMonth; i++) days.push(i);

    return (
      <div className="calendar">
        <div className="calendar-header">
          <button className="calendar-nav" onClick={() => onMonthChange(-1)} aria-label="上个月">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
            </svg>
          </button>
          <span className="calendar-title">{date.year}年 {monthNames[date.month]}</span>
          <button className="calendar-nav" onClick={() => onMonthChange(1)} aria-label="下个月">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
            </svg>
          </button>
        </div>
        <div className="calendar-weekdays">
          {weekDays.map(d => <span key={d}>{d}</span>)}
        </div>
        <div className="calendar-days">
          {days.map((day, i) => (
            <button
              key={i}
              className={`calendar-day${day === null ? ' empty' : ''}${isToday(day!) ? ' today' : ''}${isSelected(day!) ? ' selected' : ''}`}
              onClick={() => day && onDayClick(day)}
              disabled={day === null}
            >
              {day}
            </button>
          ))}
        </div>
      </div>
    );
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
        <div className="time-section">
          <label className="time-section-label">开始时间</label>
          {renderCalendar(startDate, (day) => handleDateSelect(day, false), (delta) => handleMonthChange(delta, false))}
          <input
            type="time"
            className="time-input"
            value={startTime}
            onChange={(e) => setStartTime(e.target.value)}
          />
        </div>

        {mode === 'range' && (
          <div className="time-section">
            <label className="time-section-label">结束时间</label>
            {renderCalendar(endDate, (day) => handleDateSelect(day, true), (delta) => handleMonthChange(delta, true))}
            <input
              type="time"
              className="time-input"
              value={endTime}
              onChange={(e) => setEndTime(e.target.value)}
            />
          </div>
        )}
      </div>

      <div className="time-picker-footer">
        <button className="time-btn-clear" onClick={handleClear}>
          清除
        </button>
        <button className="time-btn-confirm" onClick={handleConfirm}>
          确认
        </button>
      </div>
    </div>
  );
}

export default TimePicker;
