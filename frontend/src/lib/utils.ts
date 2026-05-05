import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** 获取浏览器本地时区 IANA 名，如 "Asia/Shanghai" */
export function getBrowserTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

export function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return '未知时间';
  // Backend returns naive UTC datetimes without timezone marker.
  // Append 'Z' so JavaScript parses it as UTC, not local time.
  const utcStr = dateStr.endsWith('Z') || /[+-]\d{2}:?\d{2}$/.test(dateStr)
    ? dateStr
    : dateStr + 'Z';
  const date = new Date(utcStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffMin < 1) return '刚刚';
  if (diffMin < 60) return `${diffMin}分钟前`;
  if (diffHour < 24) return `${diffHour}小时前`;
  if (diffDay < 7) return `${diffDay}天前`;
  return date.toLocaleDateString('zh-CN');
}

export function getTrendColor(trend: string): string {
  switch (trend) {
    case 'up':
      return 'text-red-500';
    case 'down':
      return 'text-green-500';
    default:
      return 'text-gray-400';
  }
}

export function getTrendIcon(trend: string): string {
  switch (trend) {
    case 'up':
      return '↑';
    case 'down':
      return '↓';
    default:
      return '→';
  }
}

export function getSentimentColor(sentiment: string | null): string {
  switch (sentiment) {
    case 'positive':
      return 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20';
    case 'negative':
      return 'bg-red-500/10 text-red-500 border-red-500/20';
    default:
      return 'bg-gray-500/10 text-gray-400 border-gray-500/20';
  }
}

export function getSentimentLabel(sentiment: string | null): string {
  switch (sentiment) {
    case 'positive':
      return '正面';
    case 'negative':
      return '负面';
    default:
      return '中性';
  }
}

export function isToday(dateStr: string | null): boolean {
  if (!dateStr) return false;
  const utcStr = dateStr.endsWith('Z') || /[+\-]\d{2}:?\d{2}$/.test(dateStr)
    ? dateStr
    : dateStr + 'Z';
  const date = new Date(utcStr);
  const now = new Date();
  return (
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  );
}
