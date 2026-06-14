import type { Category } from './types';

export const CATEGORIES: Category[] = ['work', 'study', 'life', 'other'];

export const CATEGORY_LABELS: Record<Category, string> = {
  work: '工作',
  study: '学习',
  life: '生活',
  other: '其他',
};
