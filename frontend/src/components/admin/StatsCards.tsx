import { FileText, Flame, Globe, Clock } from 'lucide-react';
import type { AdminStats } from '@/types';
import { cn } from '@/lib/utils';

interface StatsCardsProps {
  stats?: AdminStats | null;
  isLoading: boolean;
}

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}天 ${hours}小时`;
  if (hours > 0) return `${hours}小时 ${mins}分钟`;
  return `${mins}分钟`;
}

const cards = [
  {
    key: 'articles_today' as const,
    label: '今日采集文章数',
    icon: FileText,
    color: 'text-blue-500',
    bg: 'bg-blue-500/10',
  },
  {
    key: 'events_today' as const,
    label: '今日生成热点数',
    icon: Flame,
    color: 'text-orange-500',
    bg: 'bg-orange-500/10',
  },
  {
    key: 'sources' as const,
    label: '活跃来源 / 总来源',
    icon: Globe,
    color: 'text-emerald-500',
    bg: 'bg-emerald-500/10',
    getValue: (s: AdminStats) => `${s.active_sources} / ${s.total_sources}`,
  },
  {
    key: 'uptime' as const,
    label: '系统运行时间',
    icon: Clock,
    color: 'text-purple-500',
    bg: 'bg-purple-500/10',
    getValue: (s: AdminStats) => formatUptime(s.uptime_seconds),
  },
];

export default function StatsCards({ stats, isLoading }: StatsCardsProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => {
        const Icon = card.icon;
        let value: string | number = '--';
        if (!isLoading && stats) {
          if (card.getValue) {
            value = card.getValue(stats);
          } else if (card.key === 'articles_today') {
            value = stats.articles_today;
          } else if (card.key === 'events_today') {
            value = stats.events_today;
          }
        }

        return (
          <div
            key={card.key}
            className={cn(
              'rounded-xl border border-border bg-card p-5 transition-all',
              isLoading && 'animate-pulse'
            )}
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">{card.label}</p>
                <p className="mt-1 text-2xl font-bold">{value}</p>
              </div>
              <div className={cn('rounded-lg p-2.5', card.bg)}>
                <Icon className={cn('h-5 w-5', card.color)} />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
