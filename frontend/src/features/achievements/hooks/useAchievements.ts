import { useCallback, useEffect, useRef, useState } from 'react';
import type { AchievementDef, AchievementState } from '@/shared/types';

export const ACHIEVEMENTS: AchievementDef[] = [
  { id: 'first-task', name: '初出茅庐', description: '完成你的第一个任务', icon: '🌱' },
  { id: 'speed-demon', name: '效率达人', description: '一天内完成10个任务', icon: '⚡' },
  { id: 'streak-7', name: '永不言弃', description: '连续7天完成任务', icon: '🔥' },
];

export function useAchievements(
  initialState: AchievementState,
  onUnlockSound?: () => void,
) {
  const [state, setState] = useState(initialState);
  const [toast, setToast] = useState<AchievementDef | null>(null);
  const toastTimerRef = useRef<number | null>(null);

  useEffect(() => {
    setState(initialState);
    setToast(null);
    if (toastTimerRef.current !== null) {
      clearTimeout(toastTimerRef.current);
      toastTimerRef.current = null;
    }
  }, [initialState]);

  useEffect(() => () => {
    if (toastTimerRef.current !== null) clearTimeout(toastTimerRef.current);
  }, []);

  const applyCompletion = useCallback((
    achievementState: AchievementState,
    newlyUnlocked: string[],
  ) => {
    setState(achievementState);
    const achievement = newlyUnlocked
      .map(id => ACHIEVEMENTS.find(definition => definition.id === id))
      .find((definition): definition is AchievementDef => definition !== undefined);
    if (!achievement) return;

    setToast(achievement);
    onUnlockSound?.();
    if (toastTimerRef.current !== null) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = window.setTimeout(() => setToast(null), 3_000);
  }, [onUnlockSound]);

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
    applyCompletion,
    allAchievements: ACHIEVEMENTS,
  };
}
