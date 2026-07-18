import type { Category, FilterType } from '@/shared/types';
import ProgressRing from '@/features/stats/components/ProgressRing';
import { useI18n } from '@/features/i18n/I18nProvider';
import type { TranslationKey } from '@/features/i18n/translations';
import '../styles/Sidebar.css';

interface SidebarProps {
  categories: Category[];
  categoryLabels: Record<Category, TranslationKey>;
  categoryFilter: Category | 'all';
  setCategoryFilter: (c: Category | 'all') => void;
  filter: FilterType;
  setFilter: (f: FilterType) => void;
  stats: { total: number; active: number; completed: number };
  todayCompleted: number;
  dailyGoal: number;
  searchQuery: string;
  setSearchQuery: (q: string) => void;
}

const STATUS_TABS: { value: FilterType; label: TranslationKey }[] = [
  { value: 'all', label: 'sidebar.all' },
  { value: 'active', label: 'sidebar.active' },
  { value: 'completed', label: 'sidebar.completed' },
];

const ICON_PROPS = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.5,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

function CategoryIcon({ category }: { category: Category | 'all' }) {
  switch (category) {
    case 'all':
      return (
        <svg {...ICON_PROPS}>
          <path d="M2.25 13.5h3.86a2.25 2.25 0 0 1 2.012 1.244l.256.512a2.25 2.25 0 0 0 2.013 1.244h3.218a2.25 2.25 0 0 0 2.013-1.244l.256-.512a2.25 2.25 0 0 1 2.013-1.244h3.859m-19.5.338V18a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18v-4.162c0-.224-.034-.447-.1-.661L19.24 5.338a2.25 2.25 0 0 0-2.15-1.588H6.911a2.25 2.25 0 0 0-2.15 1.588L2.35 13.177a2.25 2.25 0 0 0-.1.661Z" />
        </svg>
      );
    case 'work':
      return (
        <svg {...ICON_PROPS}>
          <path d="M5.25 7.5h13.5A1.5 1.5 0 0 1 20.25 9v7.5a1.5 1.5 0 0 1-1.5 1.5H5.25a1.5 1.5 0 0 1-1.5-1.5V9a1.5 1.5 0 0 1 1.5-1.5Z" />
          <path d="M9 7.5V6a2.25 2.25 0 0 1 2.25-2.25h1.5A2.25 2.25 0 0 1 15 6v1.5" />
          <path d="M3.75 12h16.5" />
        </svg>
      );
    case 'study':
      return (
        <svg {...ICON_PROPS}>
          <path d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
        </svg>
      );
    case 'life':
      return (
        <svg {...ICON_PROPS}>
          <path d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z" />
        </svg>
      );
    case 'other':
      return (
        <svg viewBox="0 0 24 24" fill="currentColor" stroke="none">
          <circle cx="5" cy="12" r="1.6" />
          <circle cx="12" cy="12" r="1.6" />
          <circle cx="19" cy="12" r="1.6" />
        </svg>
      );
    default:
      return null;
  }
}

function Sidebar({
  categories,
  categoryLabels,
  categoryFilter,
  setCategoryFilter,
  filter,
  setFilter,
  stats,
  todayCompleted,
  dailyGoal,
  searchQuery,
  setSearchQuery,
}: SidebarProps) {
  const { t } = useI18n();
  const navItems: { value: Category | 'all'; label: string; count?: number }[] = [
    { value: 'all', label: t('sidebar.all'), count: stats.total },
    ...categories.map((c) => ({ value: c, label: t(categoryLabels[c]) })),
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar__search">
        <svg
          className="sidebar__search-icon"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
        </svg>
        <input
          type="text"
          placeholder={t('sidebar.search')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          aria-label={t('sidebar.searchLabel')}
        />
      </div>

      <section className="sidebar__section">
        <nav className="sidebar__nav" aria-label={t('sidebar.categoryNav')}>
          {navItems.map((item) => {
            const active = categoryFilter === item.value;
            return (
              <button
                key={item.value}
                type="button"
                className={`sidebar__nav-item${active ? ' sidebar__nav-item--active' : ''}`}
                onClick={() => setCategoryFilter(item.value)}
                aria-pressed={active}
              >
                <span className="sidebar__nav-icon">
                  <CategoryIcon category={item.value} />
                </span>
                <span className="sidebar__nav-label">{item.label}</span>
                {typeof item.count === 'number' && (
                  <span className="sidebar__nav-count">{item.count}</span>
                )}
              </button>
            );
          })}
        </nav>
      </section>

      <section className="sidebar__section">
        <div className="sidebar__filter" role="group" aria-label={t('sidebar.statusFilter')}>
          {STATUS_TABS.map((tab) => {
            const active = filter === tab.value;
            return (
              <button
                key={tab.value}
                type="button"
                className={`sidebar__filter-btn${active ? ' sidebar__filter-btn--active' : ''}`}
                onClick={() => setFilter(tab.value)}
                aria-pressed={active}
              >
                {t(tab.label)}
              </button>
            );
          })}
        </div>
      </section>

      <div className="sidebar__progress">
        <ProgressRing current={todayCompleted} goal={dailyGoal} size={48} strokeWidth={4} />
        <span className="sidebar__progress-text">
          {t('sidebar.todayGoal', { completed: todayCompleted, goal: dailyGoal })}
        </span>
      </div>
    </aside>
  );
}

export default Sidebar;
