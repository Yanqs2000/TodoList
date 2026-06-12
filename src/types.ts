export type Priority = 'low' | 'medium' | 'high';
export type FilterType = 'all' | 'active' | 'completed';

export interface TimeField {
  start: string;  // "14:30"
  end?: string;   // "15:30" (optional, for time range)
}

export interface Todo {
  id: string;
  text: string;
  completed: boolean;
  priority: Priority;
  createdAt: number;
  time?: TimeField;
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
