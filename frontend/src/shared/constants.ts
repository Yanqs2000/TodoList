import type { Category, Priority } from './types';
import type { TranslationKey } from '@/features/i18n/translations';

export const CATEGORIES: Category[] = ['work', 'study', 'life', 'other'];

export const CATEGORY_LABELS: Record<Category, TranslationKey> = {
  work: 'category.work',
  study: 'category.study',
  life: 'category.life',
  other: 'category.other',
};

export const PRIORITY_LABELS: Record<Priority, TranslationKey> = {
  low: 'priority.low',
  medium: 'priority.medium',
  high: 'priority.high',
};

export const PRIORITIES: Priority[] = ['low', 'medium', 'high'];

export const DAILY_GOAL = 10;
