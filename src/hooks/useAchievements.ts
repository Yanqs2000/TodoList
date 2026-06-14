import { useState, useCallback, useRef } from 'react';
import type { AchievementDef, AchievementState } from '../types';

const STORAGE_KEY = 'todo-achievements';

export const ACHIEVEMENTS: AchievementDef[] = [
  { id: 'first-task', name: '初出茅庐', description: '完成你的第一个任务', icon: '🌱' },
  { id: 'speed-demon', name: '效率达人', description: '一天内完成10个任务', icon: '⚡' },
  { id: 'streak-7', name: '永不言弃', description: '连续7天完成任务', icon: '🔥' },
];

function getToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function getInitialState(): AchievementState {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return JSON.parse(stored);
  } catch {}
  return { unlocked: [], streakDays: 0, lastActiveDate: '', todayCompleted: 0, todayDate: getToday() };
}

export function useAchievements(onUnlockSound?: () => void) {
  const [state, setState] = useState(getInitialState);
  const [toast, setToast] = useState<AchievementDef | null>(null);
  const toastTimerRef = useRef<number>(0);

  const checkAchievements = useCallback((completedCount: number, newUnlocked: string[]) => {
    const checks: { id: string; condition: boolean }[] = [
      { id: 'first-task', condition: completedCount >= 1 },
      { id: 'speed-demon', condition: completedCount >= 10 },
    ];

    for (const check of checks) {
      if (check.condition && !newUnlocked.includes(check.id)) {
        newUnlocked.push(check.id);
      }
    }
    return newUnlocked;
  }, []);

  const recordCompletion = useCallback(() => {
    setState(prev => {
      const today = getToday();
      let todayCompleted = prev.todayDate === today ? prev.todayCompleted + 1 : 1;
      let streakDays = prev.streakDays;

      if (prev.lastActiveDate !== today) {
        const yesterday = new Date();
        yesterday.setDate(yesterday.getDate() - 1);
        const yesterdayStr = yesterday.toISOString().slice(0, 10);
        streakDays = prev.lastActiveDate === yesterdayStr ? streakDays + 1 : 1;
      }

      let unlocked = [...prev.unlocked];
      unlocked = checkAchievements(todayCompleted, unlocked);

      if (streakDays >= 7 && !unlocked.includes('streak-7')) {
        unlocked.push('streak-7');
      }

      const newlyUnlocked = unlocked.filter(id => !prev.unlocked.includes(id));
      if (newlyUnlocked.length > 0) {
        const achievement = ACHIEVEMENTS.find(a => a.id === newlyUnlocked[0]);
        if (achievement) {
          setToast(achievement);
          onUnlockSound?.();
          clearTimeout(toastTimerRef.current);
          toastTimerRef.current = window.setTimeout(() => setToast(null), 3000);
        }
      }

      const newState: AchievementState = {
        unlocked,
        streakDays,
        lastActiveDate: today,
        todayCompleted,
        todayDate: today,
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(newState));
      return newState;
    });
  }, [checkAchievements, onUnlockSound]);

  const dismissToast = useCallback(() => {
    setToast(null);
  }, []);

  return {
    achievements: state,
    toast,
    dismissToast,
    recordCompletion,
    allAchievements: ACHIEVEMENTS,
  };
}
