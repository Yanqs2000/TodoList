import { useState, useCallback, useRef } from 'react';

export function useDragDrop(onReorder: (fromId: string, toId: string) => void) {
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);
  const lastOverIdRef = useRef<string | null>(null);

  const handleDragStart = useCallback((e: React.DragEvent, id: string) => {
    setDraggingId(id);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', id);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent, id: string) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (lastOverIdRef.current !== id) {
      lastOverIdRef.current = id;
      setOverId(id);
    }
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    if (lastOverIdRef.current !== null) {
      lastOverIdRef.current = null;
      setOverId(null);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent, toId: string) => {
    e.preventDefault();
    const fromId = e.dataTransfer.getData('text/plain');
    if (fromId && fromId !== toId) {
      onReorder(fromId, toId);
    }
    setDraggingId(null);
    setOverId(null);
    lastOverIdRef.current = null;
  }, [onReorder]);

  const handleDragEnd = useCallback(() => {
    setDraggingId(null);
    setOverId(null);
    lastOverIdRef.current = null;
  }, []);

  return {
    draggingId,
    overId,
    handleDragStart,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleDragEnd,
  };
}
