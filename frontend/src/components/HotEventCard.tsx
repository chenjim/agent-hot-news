import { Link } from 'react-router-dom';
import { TrendingUp, TrendingDown, Flame, Newspaper, Globe } from 'lucide-react';
import type { HotEvent } from '@/types';
import {
  cn,
  formatRelativeTime,
  isToday,
} from '@/lib/utils';

interface HotEventCardProps {
  event: HotEvent;
  index: number;
}

function TrendIcon({ trend, className }: { trend: string; className?: string }) {
  const sizeClass = 'h-4 w-4';
  if (trend === 'up') return <TrendingUp className={cn(sizeClass, className)} />;
  if (trend === 'down') return <TrendingDown className={cn(sizeClass, className)} />;
  return <Flame className={cn(sizeClass, className)} />;
}

export default function HotEventCard({ event, index }: HotEventCardProps) {
  const today = isToday(event.first_seen_at);

  return (
    <Link
      to={`/event/${event.id}`}
      className="group relative block overflow-hidden rounded-xl border border-border/70 bg-card transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-primary/10 hover:border-primary/40"
    >
      <div className="p-5">
        {/* Title */}
        <h3 className="mb-2 text-lg font-bold leading-snug group-hover:text-primary transition-colors">
          {event.title}
        </h3>

        {/* Summary */}
        {event.summary && (
          <p className="mb-4 line-clamp-2 min-h-[2.5rem] text-sm text-muted-foreground">
            {event.summary}
          </p>
        )}

        {/* Meta row */}
        <div className="flex flex-wrap items-center gap-3 text-xs">
          {/* Hot score */}
          <div className="flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 font-semibold text-primary">
            <TrendIcon trend={event.trend} className="text-orange-500" />
            <span>{event.hot_score.toFixed(1)}</span>
          </div>

          {/* Today badge */}
          {today && (
            <span className="rounded-full bg-orange-500 px-2 py-0.5 text-[10px] font-bold text-white">
              今日
            </span>
          )}

          {/* Articles count */}
          <div className="flex items-center gap-1 text-muted-foreground">
            <Newspaper className="h-3.5 w-3.5" />
            <span>{event.articles_count} 篇报道</span>
          </div>

          {/* Sources count */}
          <div className="flex items-center gap-1 text-muted-foreground">
            <Globe className="h-3.5 w-3.5" />
            <span>{event.sources_count} 个来源</span>
          </div>

          {/* Time */}
          <span className="ml-auto text-muted-foreground">
            {formatRelativeTime(event.last_updated_at)}
          </span>
        </div>

        {/* Entities */}
        {event.entities && event.entities.length > 0 && (
          <div className="mt-3 flex flex-nowrap gap-1.5 overflow-hidden">
            {event.entities.slice(0, 5).map((entity) => (
              <span
                key={entity}
                className="whitespace-nowrap rounded-md bg-secondary px-2 py-0.5 text-xs text-secondary-foreground"
              >
                {entity}
              </span>
            ))}
          </div>
        )}
      </div>
    </Link>
  );
}
