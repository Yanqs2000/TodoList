export type Priority = 'low' | 'medium' | 'high';
export type FilterType = 'all' | 'active' | 'completed';

export interface Todo {
  id: string;
  text: string;
  completed: boolean;
  priority: Priority;
  createdAt: number;
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
