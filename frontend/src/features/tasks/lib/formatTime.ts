import type { TimeField } from '@/shared/types';

export function formatTimeField(time: TimeField): string {
  const single = (iso: string): string => {
    if (!iso) return '';
    const [date, t] = iso.split('T');
    const [, m, d] = date.split('-');
    return `${m}/${d} ${t}`;
  };
  return time.end ? `${single(time.start)} - ${single(time.end)}` : single(time.start);
}
