import type { TimeField } from '@/shared/types';

export function formatTimeField(time: TimeField, locale = 'zh-CN', now = Date.now()): string {
  const single = (iso: string): string => {
    if (!iso) return '';
    const [date, t] = iso.split('T');
    const [year, m, d] = date.split('-').map(Number);
    const isCurrentYear = year === new Date(now).getFullYear();
    if (locale === 'zh-CN') {
      const compactDate = `${String(m).padStart(2, '0')}/${String(d).padStart(2, '0')}`;
      return `${isCurrentYear ? compactDate : `${year}/${compactDate}`} ${t}`;
    }
    const [hour, minute] = t.split(':').map(Number);
    const options: Intl.DateTimeFormatOptions = {
      month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
    };
    if (!isCurrentYear) options.year = 'numeric';
    return new Intl.DateTimeFormat(locale, options)
      .format(new Date(year, m - 1, d, hour, minute));
  };
  return time.end ? `${single(time.start)} - ${single(time.end)}` : single(time.start);
}
