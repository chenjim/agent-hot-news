import { useState, useCallback } from 'react';
import { Flame, RefreshCw } from 'lucide-react';
import Header from '@/components/Header';
import CategoryFilter from '@/components/CategoryFilter';
import HotEventCard from '@/components/HotEventCard';
import ToastNotification, { pushToast } from '@/components/ToastNotification';
import { useHotEvents } from '@/hooks/useApi';
import { useHotEventsSSE } from '@/hooks/useSSE';
import { type Category } from '@/types';
import { cn } from '@/lib/utils';

export default function HomePage() {
  const [category, setCategory] = useState<Category>('all');
  const { events, error, isLoading, mutate } = useHotEvents(category, 30);

  const handleSSEMessage = useCallback((data: unknown) => {
    if (data && typeof data === 'object' && 'event' in data) {
      const event = (data as { event: unknown }).event;
      if (event && typeof event === 'object' && 'title' in event) {
        pushToast(event as import('@/types').HotEvent);
      }
    }
  }, []);

  useHotEventsSSE(handleSSEMessage);

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="container mx-auto px-4 py-8">
        {/* Hero section */}
        <section className="mb-8">
          <div className="flex items-center justify-between">
            <div>
              <p className="mt-2 text-muted-foreground">
                AI 实时聚合 {events.length} 个正在发酵的热点事件
              </p>
            </div>
            <button
              onClick={() => mutate()}
              className={cn(
                'flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2 text-sm font-medium',
                'transition-all hover:bg-secondary',
                isLoading && 'animate-pulse'
              )}
            >
              <RefreshCw className={cn('h-4 w-4', isLoading && 'animate-spin')} />
              刷新
            </button>
          </div>
        </section>

        {/* Category filter */}
        <section className="mb-6">
          <CategoryFilter active={category} onChange={setCategory} />
        </section>

        {/* Events grid */}
        {error ? (
          <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-8 text-center">
            <p className="text-destructive">加载失败，请稍后重试</p>
          </div>
        ) : isLoading && events.length === 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="h-48 animate-pulse rounded-xl bg-muted"
              />
            ))}
          </div>
        ) : events.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
            <Flame className="mb-4 h-12 w-12 opacity-30" />
            <p>暂无热点数据</p>
            <p className="text-sm">数据采集和 AI 分析正在后台运行...</p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {events.map((event, index) => (
              <HotEventCard key={event.id} event={event} index={index} />
            ))}
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-border py-6 text-center text-sm text-muted-foreground">
        <p>今日热点 — AI 驱动的多源热点聚合</p>
      </footer>

      <ToastNotification />
    </div>
  );
}
