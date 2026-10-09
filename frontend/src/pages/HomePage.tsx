import { useState, useCallback, useEffect, useRef } from 'react';
import { Flame, Loader2 } from 'lucide-react';
import Header from '@/components/Header';
import CategoryFilter from '@/components/CategoryFilter';
import HotEventCard from '@/components/HotEventCard';
import ToastNotification, { pushToast } from '@/components/ToastNotification';
import { useHotEventsInfinite } from '@/hooks/useApi';
import { useHotEventsSSE } from '@/hooks/useSSE';
import { type Category } from '@/types';

export default function HomePage() {
  const [category, setCategory] = useState<Category>('all');
  const { events, error, isLoading, isReachingEnd, loadMore, setSize } =
    useHotEventsInfinite(category, 30);

  // 切分类时回到第一页，否则会沿用上一个分类已加载的页数
  useEffect(() => {
    setSize(1);
  }, [category, setSize]);

  const sentinelRef = useRef<HTMLDivElement | null>(null);

  // 触底自动加载下一页：observer 依赖 loadMore，每加载一页重建一次；
  // 哨兵若仍在视口内会再次触发，直到加载完或哨兵移出视口。
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) loadMore();
      },
      { rootMargin: '400px' }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [loadMore]);

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
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {events.map((event, index) => (
                <HotEventCard key={event.id} event={event} index={index} />
              ))}
            </div>

            {/* 触底哨兵：进入视口即自动加载下一页 */}
            <div
              ref={sentinelRef}
              className="flex items-center justify-center py-8 text-sm text-muted-foreground"
            >
              {isReachingEnd ? (
                <span>已经到底啦</span>
              ) : (
                <Loader2 className="h-5 w-5 animate-spin" />
              )}
            </div>
          </>
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
