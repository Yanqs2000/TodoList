import type { FilterType } from '../types';
import '../styles/FilterTabs.css';

interface FilterTabsProps {
  filter: FilterType;
  setFilter: (f: FilterType) => void;
}

const tabs: { value: FilterType; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'active', label: '未完成' },
  { value: 'completed', label: '已完成' },
];

function FilterTabs({ filter, setFilter }: FilterTabsProps) {
  return (
    <div className="filters">
      {tabs.map(tab => (
        <button
          key={tab.value}
          className={`filter-btn${filter === tab.value ? ' active' : ''}`}
          data-filter={tab.value}
          onClick={() => setFilter(tab.value)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export default FilterTabs;
