import type { FilterType, Category } from '../types';
import '../styles/FilterTabs.css';

interface FilterTabsProps {
  filter: FilterType;
  setFilter: (f: FilterType) => void;
  categoryFilter: Category | 'all';
  setCategoryFilter: (c: Category | 'all') => void;
  categories: Category[];
  categoryLabels: Record<Category, string>;
}

const tabs: { value: FilterType; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'active', label: '未完成' },
  { value: 'completed', label: '已完成' },
];

function FilterTabs({ filter, setFilter, categoryFilter, setCategoryFilter, categories, categoryLabels }: FilterTabsProps) {
  return (
    <div className="filter-area">
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
      <div className="category-filters">
        <button
          className={`category-filter-btn${categoryFilter === 'all' ? ' active' : ''}`}
          onClick={() => setCategoryFilter('all')}
        >
          全部分类
        </button>
        {categories.map(cat => (
          <button
            key={cat}
            className={`category-filter-btn${categoryFilter === cat ? ' active' : ''}`}
            onClick={() => setCategoryFilter(cat)}
          >
            {categoryLabels[cat]}
          </button>
        ))}
      </div>
    </div>
  );
}

export default FilterTabs;
