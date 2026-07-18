import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { AchievementDef, AchievementState } from '@/shared/types';
import { useI18n } from '@/features/i18n/I18nProvider';

export function useAchievements(
  initialState: AchievementState,
  onUnlockSound?: () => void,
) {
  const { t } = useI18n();
  const achievements = useMemo<AchievementDef[]>(() => [
    { id: 'first-task', name: t('achievement.first.name'), description: t('achievement.first.desc'), icon: '🌱' },
    { id: 'speed-demon', name: t('achievement.speed.name'), description: t('achievement.speed.desc'), icon: '⚡' },
    { id: 'streak-7', name: t('achievement.streak.name'), description: t('achievement.streak.desc'), icon: '🔥' },
  ], [t]);
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

  useEffect(() => {
    setToast(current => (
      current ? achievements.find(item => item.id === current.id) ?? null : null
    ));
  }, [achievements]);

  const applyCompletion = useCallback((
    achievementState: AchievementState,
    newlyUnlocked: string[],
  ) => {
    setState(achievementState);
    const achievement = newlyUnlocked
      .map(id => achievements.find(definition => definition.id === id))
      .find((definition): definition is AchievementDef => definition !== undefined);
    if (!achievement) return;

    setToast(achievement);
    onUnlockSound?.();
    if (toastTimerRef.current !== null) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = window.setTimeout(() => setToast(null), 3_000);
  }, [achievements, onUnlockSound]);

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
    allAchievements: achievements,
  };
}
