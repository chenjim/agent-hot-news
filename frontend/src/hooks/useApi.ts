import useSWR, { mutate as globalMutate } from 'swr';
import useSWRInfinite from 'swr/infinite';
import { useCallback } from 'react';
import type { HotEvent, HotEventDetail, Category, Source, AdminStats, TaskLog } from '@/types';
import { getBrowserTimezone } from '@/lib/utils';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:51180/api/v1';

// 读令牌：构建期由 VITE_READ_TOKEN 注入。展示页只读，写接口不在此暴露。
const READ_TOKEN: string = import.meta.env.VITE_READ_TOKEN || '';

/**
 * 统一给 URL 附带读令牌。
 * EventSource 带不了 header，SSE 只能走 query，所以 fetch 也一并支持。
 */
export function withReadToken(url: string): string {
  if (!READ_TOKEN) return url;
  return url + (url.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(READ_TOKEN);
}

async function fetcher<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: READ_TOKEN ? { 'X-Read-Token': READ_TOKEN } : undefined,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}

export function useHotEvents(category: Category = 'all', limit: number = 30) {
  const params = new URLSearchParams();
  if (category !== 'all') params.set('category', category);
  params.set('limit', String(limit));
  params.set('tz', getBrowserTimezone());

  const { data, error, isLoading, mutate } = useSWR<HotEvent[]>(
    `${API_BASE}/hot-events?${params.toString()}`,
    fetcher,
    { refreshInterval: 60000, refreshWhenHidden: false }
  );

  return { events: data || [], error, isLoading, mutate };
}

// 无限滚动最多加载 10 页（30/页 = 300 条），与后端 limit 上限 300 对齐
export const HOT_EVENTS_MAX_PAGES = 10;

/**
 * 无限滚动版热点列表：每页 pageSize 条，滑到底部再拉下一页。
 * ``events`` 是已加载各页拼起来的数组；``loadMore`` 由页面在触底时调用。
 */
export function useHotEventsInfinite(category: Category = 'all', pageSize: number = 30) {
  const getKey = (pageIndex: number, previousPage: HotEvent[] | null) => {
    // 到底了（上一页不满 / 已到 10 页上限）就不再请求
    if (pageIndex >= HOT_EVENTS_MAX_PAGES) return null;
    if (previousPage && previousPage.length < pageSize) return null;

    const params = new URLSearchParams();
    if (category !== 'all') params.set('category', category);
    params.set('limit', String(pageSize));
    params.set('offset', String(pageIndex * pageSize));
    params.set('tz', getBrowserTimezone());
    return `${API_BASE}/hot-events?${params.toString()}`;
  };

  const { data, error, isLoading, isValidating, size, setSize, mutate } =
    useSWRInfinite<HotEvent[]>(getKey, fetcher, {
      refreshInterval: 60000,
      refreshWhenHidden: false,
      revalidateFirstPage: true,
    });

  const events = data ? data.flat() : [];
  const isReachingEnd =
    (!!data && data.length > 0 && data[data.length - 1].length < pageSize) ||
    (!!data && data.length >= HOT_EVENTS_MAX_PAGES);

  const loadMore = useCallback(() => {
    if (!isReachingEnd && !isValidating) setSize(size + 1);
  }, [isReachingEnd, isValidating, setSize, size]);

  return { events, error, isLoading, isValidating, isReachingEnd, loadMore, setSize, mutate };
}

export function useHotEventDetail(id: number | null) {
  const { data, error, isLoading } = useSWR<HotEventDetail>(
    id ? `${API_BASE}/hot-events/${id}` : null,
    fetcher
  );

  return { event: data, error, isLoading };
}

// Admin hooks：只读看板（统计、来源健康度、任务日志）
export function useAdminStats() {
  const params = new URLSearchParams();
  params.set('tz', getBrowserTimezone());

  const { data, error, isLoading, mutate } = useSWR<AdminStats>(
    `${API_BASE}/admin/stats?${params.toString()}`,
    fetcher,
    { refreshInterval: 30000, refreshWhenHidden: false }
  );
  return { stats: data, error, isLoading, mutate };
}

export function useSources() {
  const { data, error, isLoading, mutate } = useSWR<Source[]>(`${API_BASE}/sources`, fetcher, {
    refreshInterval: 30000,
    refreshWhenHidden: false,
  });
  return { sources: data || [], error, isLoading, mutate };
}

export function useTaskLogs() {
  const { data, error, isLoading, mutate } = useSWR<TaskLog[]>(`${API_BASE}/admin/logs`, fetcher, {
    refreshInterval: 10000,
    refreshWhenHidden: false,
  });
  return { logs: data || [], error, isLoading, mutate };
}

export { globalMutate };
