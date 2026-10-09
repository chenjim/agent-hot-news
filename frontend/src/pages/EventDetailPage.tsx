import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, TrendingUp, TrendingDown, Flame, Globe, Newspaper, Search } from 'lucide-react';
import Header from '@/components/Header';
import { useHotEventDetail } from '@/hooks/useApi';
import { cn, getSentimentColor, getSentimentLabel } from '@/lib/utils';

function TrendIcon({ trend, className }: { trend: string; className?: string }) {
  const sizeClass = 'h-5 w-5';
  if (trend === 'up') return <TrendingUp className={cn(sizeClass, className)} />;
  if (trend === 'down') return <TrendingDown className={cn(sizeClass, className)} />;
  return <Flame className={cn(sizeClass, className)} />;
}

export default function EventDetailPage() {
  const { id } = useParams<{ id: string }>();
  const eventId = id && /^\d+$/.test(id) ? Number(id) : null;
  const { event, error, isLoading } = useHotEventDetail(eventId);

  if (id && eventId === null) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-4 py-20 text-center">
          <p className="text-muted-foreground">事件不存在</p>
          <Link to="/" className="mt-4 inline-block text-primary hover:underline">
            返回首页
          </Link>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-4 py-20 text-center">
          <p className="text-destructive">加载详情失败</p>
          <Link to="/" className="mt-4 inline-block text-primary hover:underline">
            返回首页
          </Link>
        </div>
      </div>
    );
  }

  if (isLoading || !event) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-4 py-8">
          <div className="h-8 w-32 animate-pulse rounded bg-muted" />
          <div className="mt-6 h-48 animate-pulse rounded-xl bg-muted" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="container mx-auto px-4 py-8">
        {/* Back button */}
        <Link
          to="/"
          className="mb-6 inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-primary"
        >
          <ArrowLeft className="h-4 w-4" />
          返回热点列表
        </Link>

        {/* Event header */}
        <section className="mb-8 rounded-2xl border border-border bg-card p-6 sm:p-8">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex-1">
              <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
                {event.title}
              </h1>
              {event.summary && (
                <p className="mt-3 text-lg text-muted-foreground leading-relaxed">
                  {event.summary}
                </p>
              )}
            </div>
            <div className="flex items-center gap-2 rounded-full bg-primary/10 px-4 py-2 text-primary">
              <TrendIcon trend={event.trend} className="text-orange-500" />
              <span className="text-xl font-bold">{event.hot_score.toFixed(1)}</span>
            </div>
          </div>

          {/* Meta tags */}
          <div className="mt-6 flex flex-wrap items-center gap-3">
            {event.sentiment && (
              <span className={cn('rounded-full border px-3 py-1 text-sm', getSentimentColor(event.sentiment))}>
                {getSentimentLabel(event.sentiment)}
              </span>
            )}
            {event.category && (
              <span className="rounded-full bg-secondary px-3 py-1 text-sm text-secondary-foreground">
                {event.category}
              </span>
            )}
            <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Newspaper className="h-4 w-4" />
              <span>{event.articles_count} 篇报道</span>
            </div>
            <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Globe className="h-4 w-4" />
              <span>{event.sources_count} 个来源</span>
            </div>
          </div>

          {/* Entities */}
          {event.entities && event.entities.length > 0 && (
            <div className="mt-4">
              <p className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                关键实体
              </p>
              <div className="flex flex-wrap gap-2">
                {event.entities.map((entity) => (
                  <span
                    key={entity}
                    className="rounded-lg bg-secondary px-3 py-1.5 text-sm font-medium text-secondary-foreground"
                  >
                    {entity}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* Detailed summary */}
        {event.detail && (
          <section className="mb-8 rounded-2xl border border-border bg-card p-6 sm:p-8">
            <h2 className="mb-3 text-lg font-bold">详细简介</h2>
            <p className="text-base leading-relaxed text-muted-foreground whitespace-pre-line">
              {event.detail}
            </p>
          </section>
        )}

        {/* Sources */}
        <section>
          <h2 className="mb-4 text-lg font-bold">来源报道</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {event.sources.length === 0 ? (
              <div className="rounded-xl border border-border bg-card p-4 text-center text-sm text-muted-foreground sm:col-span-2 lg:col-span-3">
                暂无来源数据
              </div>
            ) : (
              event.sources.map((source, i) => {
                const bingSearchUrl = `https://www.bing.com/search?q=${encodeURIComponent(source.title)}`;
                const isHttp =
                  source.url.startsWith('http://') || source.url.startsWith('https://');
                // 后端探测过可浏览性：伪 URL / 打不开（403、超时、非网页）→ 必应搜索兜底
                const linkUrl = isHttp && source.browsable !== false ? source.url : bingSearchUrl;
                const useFallback = linkUrl !== source.url;
                return (
                  <div
                    key={i}
                    className="rounded-lg border border-border bg-card transition-all hover:border-primary/30 hover:shadow-md"
                  >
                    <a
                      href={linkUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block p-3"
                      title={useFallback ? '原文链接不可达，已改为搜索该标题' : '打开原文'}
                    >
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-1 text-xs font-medium text-primary">
                          {source.name}
                          {useFallback && (
                            <span className="inline-flex items-center gap-0.5 rounded bg-secondary px-1 py-0.5 text-[10px] text-muted-foreground">
                              <Search className="h-2.5 w-2.5" />
                              搜索
                            </span>
                          )}
                        </span>
                        <span className="text-xs text-muted-foreground">{source.hot_score.toFixed(0)}</span>
                      </div>
                      <p className="mt-1 line-clamp-2 text-sm">{source.title}</p>
                    </a>
                  </div>
                );
              })
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
