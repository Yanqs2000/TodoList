import type { Category, Priority } from './types';

export const CATEGORIES: Category[] = ['work', 'study', 'life', 'other'];

export const CATEGORY_LABELS: Record<Category, string> = {
  work: '工作',
  study: '学习',
  life: '生活',
  other: '其他',
};

export const PRIORITY_LABELS: Record<Priority, string> = {
  low: '低',
  medium: '中',
  high: '高',
};

export const PRIORITIES: Priority[] = ['low', 'medium', 'high'];

export const DAILY_GOAL = 10;
