import { useState, useRef, useEffect } from 'react';
import type { TimeField } from '@/shared/types';
import '../styles/TimePicker.css';
import { useI18n } from '@/features/i18n/I18nProvider';

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

function parseStart(iso: string): { year: number; month: number; day: number; time: string } {
  if (!iso) {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, '0');
    const mm = String(now.getMinutes()).padStart(2, '0');
    return { year: now.getFullYear(), month: now.getMonth(), day: now.getDate(), time: `${hh}:${mm}` };
  }
  const [datePart, timePart] = iso.split('T');
  const [year, month, day] = datePart.split('-').map(Number);
  return { year, month: month - 1, day, time: timePart || '09:00' };
}

function parseEnd(iso: string, fallbackDate: { year: number; month: number; day: number }): { year: number; month: number; day: number; time: string } {
  if (!iso) return { ...fallbackDate, time: '18:00' };
  const [datePart, timePart] = iso.split('T');
  const [year, month, day] = datePart.split('-').map(Number);
  return { year, month: month - 1, day, time: timePart || '18:00' };
}

const hours = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'));
const minutes = Array.from({ length: 60 }, (_, i) => String(i).padStart(2, '0'));

function TimeScroller({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: string[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const itemHeight = 32;

  useEffect(() => {
    if (ref.current) {
      const idx = options.indexOf(value);
      ref.current.scrollTop = idx * itemHeight;
    }
  }, [value, options, itemHeight]);

  return (
    <div className="time-scroller" ref={ref}>
      {options.map(opt => (
        <button
          key={opt}
          className={`time-scroller-item${opt === value ? ' selected' : ''}`}
          onClick={() => onChange(opt)}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}

function TimePicker({ time, onTimeChange, onClose }: TimePickerProps) {
  const { t, locale } = useI18n();
  const [mode, setMode] = useState<'point' | 'range'>(time?.end ? 'range' : 'point');
  const startParsed = parseStart(time?.start || '');
  const endParsed = parseEnd(time?.end || '', startParsed);

  const [startDate, setStartDate] = useState(startParsed);
  const [endDate, setEndDate] = useState(endParsed);
  const [startHour, setStartHour] = useState(startParsed.time.split(':')[0] || '09');
  const [startMinute, setStartMinute] = useState(startParsed.time.split(':')[1] || '00');
  const [endHour, setEndHour] = useState(endParsed.time.split(':')[0] || '18');
  const [endMinute, setEndMinute] = useState(endParsed.time.split(':')[1] || '00');
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
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
    const startTime = `${startHour}:${startMinute}`;
    const endTime = `${endHour}:${endMinute}`;
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

    const weekDays = locale === 'zh-CN'
      ? [
          t('time.weekdaySun'), t('time.weekdayMon'), t('time.weekdayTue'),
          t('time.weekdayWed'), t('time.weekdayThu'), t('time.weekdayFri'),
          t('time.weekdaySat'),
        ]
      : Array.from({ length: 7 }, (_, day) => (
          new Intl.DateTimeFormat(locale, { weekday: 'short' }).format(new Date(2026, 5, 7 + day))
        ));
    const monthName = locale === 'zh-CN'
      ? t('time.monthTitle', { year: date.year, month: date.month + 1 })
      : new Intl.DateTimeFormat(locale, { month: 'long', year: 'numeric' })
          .format(new Date(date.year, date.month, 1));

    return (
      <div className="calendar">
        <div className="calendar-header">
          <button className="calendar-nav" onClick={() => onMonthChange(-1)} aria-label={t('time.previousMonth')}>
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
            </svg>
          </button>
          <span className="calendar-title">{monthName}</span>
          <button className="calendar-nav" onClick={() => onMonthChange(1)} aria-label={t('time.nextMonth')}>
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
            </svg>
          </button>
        </div>
        <div className="calendar-weekdays">
          {weekDays.map(d => <span key={d}>{d}</span>)}
        </div>
        <div className="calendar-days">
          {Array.from({ length: daysInMonth }, (_, i) => i + 1).map(day => (
            <button
              key={day}
              className={`calendar-day${isToday(day) ? ' today' : ''}${isSelected(day) ? ' selected' : ''}`}
              style={{ gridColumn: (firstDay + day - 1) % 7 + 1 }}
              onClick={() => onDayClick(day)}
            >
              {day}
            </button>
          ))}
        </div>
      </div>
    );
  };

  const renderTimeScroller = (hour: string, minute: string, setHour: (h: string) => void, setMinute: (m: string) => void) => (
    <div className="time-scrollers">
      <TimeScroller value={hour} onChange={setHour} options={hours} />
      <span className="time-separator">:</span>
      <TimeScroller value={minute} onChange={setMinute} options={minutes} />
    </div>
  );

  return (
    <div className="time-picker" ref={ref}>
      <div className="time-picker-header">
        <button
          className={`time-mode-btn${mode === 'point' ? ' active' : ''}`}
          onClick={() => setMode('point')}
        >
          {t('time.point')}
        </button>
        <button
          className={`time-mode-btn${mode === 'range' ? ' active' : ''}`}
          onClick={() => setMode('range')}
        >
          {t('time.range')}
        </button>
      </div>

      <div className="time-picker-body">
        <div className="time-section">
          <label className="time-section-label">{t('time.start')}</label>
          {renderCalendar(startDate, (day) => handleDateSelect(day, false), (delta) => handleMonthChange(delta, false))}
          {renderTimeScroller(startHour, startMinute, setStartHour, setStartMinute)}
        </div>

        {mode === 'range' && (
          <div className="time-section">
            <label className="time-section-label">{t('time.end')}</label>
            {renderCalendar(endDate, (day) => handleDateSelect(day, true), (delta) => handleMonthChange(delta, true))}
            {renderTimeScroller(endHour, endMinute, setEndHour, setEndMinute)}
          </div>
        )}
      </div>

      <div className="time-picker-footer">
        <button className="time-btn-clear" onClick={handleClear}>
          {t('time.clear')}
        </button>
        <button className="time-btn-confirm" onClick={handleConfirm}>
          {t('common.confirm')}
        </button>
      </div>
    </div>
  );
}

export default TimePicker;
