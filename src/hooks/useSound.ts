import { useState, useCallback, useRef } from 'react';

const STORAGE_KEY = 'todo-muted';

function getInitialMuted(): boolean {
  return localStorage.getItem(STORAGE_KEY) === 'true';
}

function createAudioContext(): AudioContext | null {
  try {
    return new (window.AudioContext || (window as any).webkitAudioContext)();
  } catch {
    return null;
  }
}

export function useSound() {
  const [muted, setMutedState] = useState(getInitialMuted);
  const ctxRef = useRef<AudioContext | null>(null);

  const getCtx = useCallback(() => {
    if (!ctxRef.current) ctxRef.current = createAudioContext();
    return ctxRef.current;
  }, []);

  const playTone = useCallback((frequency: number, duration: number, type: OscillatorType = 'sine', volume = 0.15) => {
    if (muted) return;
    const ctx = getCtx();
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

  const toggleMuted = useCallback(() => {
    setMutedState(prev => {
      const next = !prev;
      localStorage.setItem(STORAGE_KEY, String(next));
      return next;
    });
  }, []);

  return { muted, toggleMuted, playComplete, playDelete, playAchievement };
}
