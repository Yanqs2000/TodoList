import type { TimeField } from '@/shared/types';

export function formatTimeField(time: TimeField, locale = 'zh-CN'): string {
  const single = (iso: string): string => {
    if (!iso) return '';
    const [date, t] = iso.split('T');
    const [, m, d] = date.split('-');
    if (locale === 'zh-CN') return `${m}/${d} ${t}`;
    const [year] = date.split('-').map(Number);
    const [hour, minute] = t.split(':').map(Number);
    return new Intl.DateTimeFormat(locale, {
      month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
    }).format(new Date(year, Number(m) - 1, Number(d), hour, minute));
  };
  return time.end ? `${single(time.start)} - ${single(time.end)}` : single(time.start);
}
