import { useState, useCallback, useEffect, useRef } from 'react';
import type { TodoApi } from '@/shared/api/contracts';

function createAudioContext(): AudioContext | null {
  try {
    return new (window.AudioContext || (window as any).webkitAudioContext)();
  } catch {
    return null;
  }
}

export function useSound(
  initialMuted: boolean,
  api: TodoApi,
  onError: (error: unknown) => void,
) {
  const [muted, setMutedState] = useState(initialMuted);
  const ctxRef = useRef<AudioContext | null>(null);
  const mountedRef = useRef(true);
  const committedRef = useRef(initialMuted);
  const intendedRef = useRef(initialMuted);
  const latestIntentRef = useRef(0);
  const generationRef = useRef(0);
  const queueRef = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    committedRef.current = initialMuted;
    intendedRef.current = initialMuted;
    latestIntentRef.current += 1;
    generationRef.current += 1;
    queueRef.current = Promise.resolve();
    setMutedState(initialMuted);
  }, [api, initialMuted]);

  const getCtx = useCallback(async () => {
    if (!ctxRef.current) ctxRef.current = createAudioContext();
    if (ctxRef.current?.state === 'suspended') {
      await ctxRef.current.resume();
    }
    return ctxRef.current;
  }, []);

  const playTone = useCallback(async (frequency: number, duration: number, type: OscillatorType = 'sine', volume = 0.15) => {
    if (muted) return;
    const ctx = await getCtx();
    if (!ctx) return;

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(frequency, ctx.currentTime);
    gain.gain.setValueAtTime(volume, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + duration);
  }, [muted, getCtx]);

  const playComplete = useCallback(() => {
    playTone(523, 0.1, 'sine', 0.12);
    setTimeout(() => playTone(659, 0.1, 'sine', 0.12), 60);
    setTimeout(() => playTone(784, 0.15, 'sine', 0.1), 120);
  }, [playTone]);

  const playDelete = useCallback(() => {
    playTone(300, 0.08, 'square', 0.08);
  }, [playTone]);

  const playAchievement = useCallback(() => {
    playTone(523, 0.12, 'sine', 0.15);
    setTimeout(() => playTone(659, 0.12, 'sine', 0.15), 100);
    setTimeout(() => playTone(784, 0.12, 'sine', 0.15), 200);
    setTimeout(() => playTone(1047, 0.2, 'sine', 0.12), 300);
  }, [playTone]);

  // Gentle ~5s reminder: five C5+E5 chimes roughly one second apart.
  const playReminder = useCallback(() => {
    for (let i = 0; i < 5; i++) {
      const delay = i * 1000;
      setTimeout(() => playTone(523, 0.6, 'sine', 0.12), delay);
      setTimeout(() => playTone(659, 0.6, 'sine', 0.10), delay + 80);
    }
  }, [playTone]);

  const toggleMuted = useCallback((): Promise<boolean> => {
    const next = !intendedRef.current;
    intendedRef.current = next;
    const intent = ++latestIntentRef.current;
    const generation = generationRef.current;
    const operation = queueRef.current.then(async () => {
      let succeeded = false;
      try {
        const settings = await api.updateSettings({ muted: next });
        if (mountedRef.current && generation === generationRef.current) {
          committedRef.current = settings.muted;
          succeeded = true;
        }
      } catch (error) {
        if (mountedRef.current && generation === generationRef.current) onError(error);
      }
      if (
        mountedRef.current
        && generation === generationRef.current
        && intent === latestIntentRef.current
      ) {
        intendedRef.current = committedRef.current;
        setMutedState(committedRef.current);
      }
      return succeeded;
    });
    queueRef.current = operation.then(() => undefined);
    return operation;
  }, [api, onError]);

  return { muted, toggleMuted, playComplete, playDelete, playAchievement, playReminder };
}
