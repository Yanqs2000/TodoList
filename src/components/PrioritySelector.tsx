import type { Priority } from '../types';
import '../styles/PrioritySelector.css';

interface PrioritySelectorProps {
  priority: Priority;
  setPriority: (p: Priority) => void;
}

const options: { value: Priority; label: string }[] = [
  { value: 'low', label: '低优先级' },
  { value: 'medium', label: '中优先级' },
  { value: 'high', label: '高优先级' },
];

function PrioritySelector({ priority, setPriority }: PrioritySelectorProps) {
  return (
    <div className="priority-row">
      {options.map(opt => (
        <button
          key={opt.value}
          className={`priority-btn${priority === opt.value ? ' active' : ''}`}
          data-priority={opt.value}
          onClick={() => setPriority(opt.value)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export default PrioritySelector;
