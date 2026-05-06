import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, TrendingUp, TrendingDown, Flame, Clock, Globe, Newspaper } from 'lucide-react';
import Header from '@/components/Header';
import { useHotEventDetail } from '@/hooks/useApi';
import { cn, formatRelativeTime, getSentimentColor, getSentimentLabel } from '@/lib/utils';

function TrendIcon({ trend, className }: { trend: string; className?: string }) {
  const sizeClass = 'h-5 w-5';
  if (trend === 'up') return <TrendingUp className={cn(sizeClass, className)} />;
  if (trend === 'down') return <TrendingDown className={cn(sizeClass, className)} />;
  return <Flame className={cn(sizeClass, className)} />;
}

export default function EventDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { event, error, isLoading } = useHotEventDetail(id ? parseInt(id) : null);

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

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Timeline */}
          <section className="lg:col-span-2">
            <h2 className="mb-4 text-lg font-bold">传播时间线</h2>
            <div className="rounded-xl border border-border bg-card p-4">
              {event.timeline.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">暂无时间线数据</p>
              ) : (
                <div className="relative space-y-0">
                  {event.timeline.map((item, i) => (
                    <div key={i} className="flex gap-4 pb-6 last:pb-0">
                      <div className="flex flex-col items-center">
                        <div className="h-2.5 w-2.5 rounded-full bg-primary" />
                        {i < event.timeline.length - 1 && (
                          <div className="mt-1 h-full w-px bg-border" />
                        )}
                      </div>
                      <div className="flex-1 pb-2">
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Clock className="h-3 w-3" />
                          <span>{item.time ? formatRelativeTime(item.time) : '未知时间'}</span>
                          <span className="rounded bg-secondary px-1.5 py-0.5">{item.source}</span>
                        </div>
                        <p className="mt-1 text-sm">{item.title}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          {/* Sources sidebar */}
          <section>
            <h2 className="mb-4 text-lg font-bold">来源报道</h2>
            <div className="space-y-3">
              {event.sources.length === 0 ? (
                <div className="rounded-xl border border-border bg-card p-4 text-center text-sm text-muted-foreground">
                  暂无来源数据
                </div>
              ) : (
                event.sources.map((source, i) => {
                  const baiduSearchUrl = `https://www.baidu.com/s?ie=utf-8&wd=${encodeURIComponent(source.title)}`;
                  const isTianapi = !source.url || source.url.startsWith('tianapi://');
                  return isTianapi ? (
                    <a
                      key={i}
                      href={baiduSearchUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block rounded-lg border border-border bg-card p-3 transition-all hover:border-primary/30 hover:shadow-md"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-primary">{source.name}</span>
                        <span className="text-xs text-muted-foreground">{source.hot_score.toFixed(0)}</span>
                      </div>
                      <p className="mt-1 line-clamp-2 text-sm">{source.title}</p>
                    </a>
                  ) : (
                    <a
                      key={i}
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block rounded-lg border border-border bg-card p-3 transition-all hover:border-primary/30 hover:shadow-md"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-primary">{source.name}</span>
                        <span className="text-xs text-muted-foreground">{source.hot_score.toFixed(0)}</span>
                      </div>
                      <p className="mt-1 line-clamp-2 text-sm">{source.title}</p>
                    </a>
                  );
                })
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
