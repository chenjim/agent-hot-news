import { Link } from 'react-router-dom';
import { TrendingUp, TrendingDown, Minus, Newspaper, Globe } from 'lucide-react';
import type { HotEvent } from '@/types';
import {
  cn,
  formatRelativeTime,
  getSentimentColor,
  getSentimentLabel,
  isToday,
} from '@/lib/utils';
import TrendSparkline from './TrendSparkline';

interface HotEventCardProps {
  event: HotEvent;
  index: number;
}

function TrendIcon({ trend }: { trend: string }) {
  if (trend === 'up') return <TrendingUp className="h-4 w-4" />;
  if (trend === 'down') return <TrendingDown className="h-4 w-4" />;
  return <Minus className="h-4 w-4" />;
}

export default function HotEventCard({ event, index }: HotEventCardProps) {
  const rankColors = [
    'from-orange-500 to-red-600',
    'from-amber-400 to-orange-500',
    'from-yellow-400 to-amber-500',
  ];
  const rankGradient = index < 3 ? rankColors[index] : 'from-gray-400 to-gray-500';
  const today = isToday(event.first_seen_at);

  return (
    <Link
      to={`/event/${event.id}`}
      className={cn(
        'group relative block overflow-hidden rounded-xl border border-border/50 bg-card',
        'transition-all duration-300 hover:-translate-y-1 hover:shadow-xl hover:border-primary/20'
      )}
    >
      {/* Rank badge */}
      <div
        className={cn(
          'absolute -right-8 -top-8 flex h-20 w-20 items-end justify-start rounded-full bg-gradient-to-br p-3 text-xs font-bold text-white opacity-90',
          rankGradient
        )}
      >
        #{index + 1}
      </div>

      <div className="p-5">
        {/* Title */}
        <h3 className="mb-2 text-lg font-bold leading-snug group-hover:text-primary transition-colors">
          {event.title}
        </h3>

        {/* Summary */}
        {event.summary && (
          <p className="mb-4 line-clamp-2 text-sm text-muted-foreground">
            {event.summary}
          </p>
        )}

        {/* Meta row */}
        <div className="flex flex-wrap items-center gap-3 text-xs">
          {/* Hot score */}
          <div className="flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 font-semibold text-primary">
            <TrendIcon trend={event.trend} />
            <span>{event.hot_score.toFixed(1)}</span>
          </div>

          {/* Today badge */}
          {today && (
            <span className="rounded-full bg-orange-500 px-2 py-0.5 text-[10px] font-bold text-white">
              今日
            </span>
          )}

          {/* Sentiment */}
          {event.sentiment && (
            <span
              className={cn(
                'rounded-full border px-2.5 py-1',
                getSentimentColor(event.sentiment)
              )}
            >
              {getSentimentLabel(event.sentiment)}
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

        {/* Trend sparkline */}
        <div className="mt-3">
          <TrendSparkline data={event.trend_data || undefined} />
        </div>

        {/* Entities */}
        {event.entities && event.entities.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {event.entities.slice(0, 5).map((entity) => (
              <span
                key={entity}
                className="rounded-md bg-secondary px-2 py-0.5 text-xs text-secondary-foreground"
              >
                {entity}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Bottom gradient bar for top 3 */}
      {index < 3 && (
        <div
          className={cn('h-1 w-full bg-gradient-to-r', rankGradient)}
        />
      )}
    </Link>
  );
}
