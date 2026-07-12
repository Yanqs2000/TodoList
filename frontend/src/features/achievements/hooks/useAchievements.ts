import { useState, useCallback, useRef, useEffect } from 'react';
import type { AchievementDef, AchievementState } from '@/shared/types';
import { safeSetItem, safeGetItem } from '@/shared/lib/storage';

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
  const fallback: AchievementState = {
    unlocked: [],
    streakDays: 0,
    lastActiveDate: '',
    todayCompleted: 0,
    todayDate: getToday(),
  };
  const raw = safeGetItem(STORAGE_KEY);
  if (!raw) return fallback;
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return fallback;
    return {
      unlocked: Array.isArray(parsed.unlocked) ? parsed.unlocked.filter((x: unknown): x is string => typeof x === 'string') : [],
      streakDays: typeof parsed.streakDays === 'number' ? parsed.streakDays : 0,
      lastActiveDate: typeof parsed.lastActiveDate === 'string' ? parsed.lastActiveDate : '',
      todayCompleted: typeof parsed.todayCompleted === 'number' ? parsed.todayCompleted : 0,
      todayDate: typeof parsed.todayDate === 'string' ? parsed.todayDate : getToday(),
    };
  } catch {
    return fallback;
  }
}

export function useAchievements(onUnlockSound?: () => void) {
  const [state, setState] = useState(getInitialState);
  const [toast, setToast] = useState<AchievementDef | null>(null);
  const toastTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current !== null) {
        clearTimeout(toastTimerRef.current);
      }
    };
  }, []);

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
      const sameDay = prev.todayDate === today;
      const todayCompleted = sameDay ? prev.todayCompleted + 1 : 1;
      let streakDays = prev.streakDays;

      if (!sameDay) {
        const yesterday = new Date();
        yesterday.setDate(yesterday.getDate() - 1);
        const yesterdayStr = yesterday.toISOString().slice(0, 10);
        streakDays = prev.lastActiveDate === yesterdayStr ? streakDays + 1 : 1;
      } else if (prev.lastActiveDate !== today) {
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
          if (toastTimerRef.current !== null) clearTimeout(toastTimerRef.current);
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
      safeSetItem(STORAGE_KEY, JSON.stringify(newState));
      return newState;
    });
  }, [checkAchievements, onUnlockSound]);

  const dismissToast = useCallback(() => {
    setToast(null);
    if (toastTimerRef.current !== null) {
      clearTimeout(toastTimerRef.current);
      toastTimerRef.current = null;
    }
  }, []);

  return {
    achievements: state,
    toast,
    dismissToast,
    recordCompletion,
    allAchievements: ACHIEVEMENTS,
  };
}
