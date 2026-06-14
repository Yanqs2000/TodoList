export type Priority = 'low' | 'medium' | 'high';
export type FilterType = 'all' | 'active' | 'completed';
export type Category = 'work' | 'study' | 'life' | 'other';

export interface TimeField {
  start: string;  // ISO datetime: "2026-06-15T14:30"
  end?: string;   // ISO datetime for range end: "2026-06-15T15:30"
}

export interface Todo {
  id: string;
  text: string;
  completed: boolean;
  priority: Priority;
  createdAt: number;
  time?: TimeField;
  category?: Category;
  notes?: string;
}

export interface AchievementDef {
  id: string;
  name: string;
  description: string;
  icon: string;
}

export interface AchievementState {
  unlocked: string[];
  streakDays: number;
  lastActiveDate: string;
  todayCompleted: number;
  todayDate: string;
}
