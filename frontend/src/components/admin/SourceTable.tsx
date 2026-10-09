import { AlertCircle, CheckCircle2, PauseCircle } from 'lucide-react';
import type { SourceHealth } from '@/types';
import { cn, formatRelativeTime } from '@/lib/utils';

interface SourceTableProps {
  sources: SourceHealth[];
  isLoading: boolean;
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { icon: React.ElementType; color: string }> = {
    active: { icon: CheckCircle2, color: 'text-emerald-500 bg-emerald-500/10' },
    error: { icon: AlertCircle, color: 'text-red-500 bg-red-500/10' },
    paused: { icon: PauseCircle, color: 'text-amber-500 bg-amber-500/10' },
  };
  const { icon: Icon, color } = config[status] || config.paused;
  const labelMap: Record<string, string> = { active: '正常', error: '错误', paused: '暂停' };

  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium', color)}>
      <Icon className="h-3.5 w-3.5" />
      {labelMap[status] || status}
    </span>
  );
}

/** 来源状态一览（只读）。增删改与手动采集走后端写接口，页面不再提供入口。 */
export default function SourceTable({ sources, isLoading }: SourceTableProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold">来源状态</h2>
        <span className="text-xs text-muted-foreground">只读</span>
      </div>

      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="px-4 py-3 text-left font-medium">名称</th>
                <th className="px-4 py-3 text-left font-medium">状态</th>
                <th className="px-4 py-3 text-left font-medium">最后采集</th>
                <th className="px-4 py-3 text-left font-medium">最近错误</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && sources.length === 0 ? (
                Array.from({ length: 4 }).map((_, i) => (
                  <tr key={i} className="border-b border-border last:border-0">
                    <td colSpan={4} className="px-4 py-4">
                      <div className="h-6 animate-pulse rounded bg-muted" />
                    </td>
                  </tr>
                ))
              ) : sources.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-12 text-center text-muted-foreground">
                    暂无来源数据
                  </td>
                </tr>
              ) : (
                sources.map((source) => (
                  <tr
                    key={source.name}
                    className="border-b border-border last:border-0 transition-colors hover:bg-muted/30"
                  >
                    <td className="px-4 py-3 font-medium">{source.name}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={source.status || 'paused'} />
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-muted-foreground">
                        {formatRelativeTime(source.last_fetched_at)}
                      </span>
                      {source.fetched_today != null && source.fetched_today > 0 && (
                        <span className="ml-2 rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">
                          +{source.fetched_today}
                        </span>
                      )}
                    </td>
                    <td className="max-w-xs truncate px-4 py-3 text-xs text-muted-foreground">
                      {source.last_error || '—'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
