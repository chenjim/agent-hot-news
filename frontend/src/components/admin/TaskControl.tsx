import { useState } from 'react';
import { Zap, Brain, Activity, CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import type { TaskLog } from '@/types';
import { cn, formatRelativeTime } from '@/lib/utils';

interface TaskControlProps {
  logs: TaskLog[];
  isLoading: boolean;
  onTriggerFetch: () => Promise<void>;
  onTriggerAI: () => Promise<void>;
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'success') return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
  if (status === 'running') return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />;
  return <XCircle className="h-4 w-4 text-red-500" />;
}

export default function TaskControl({ logs, isLoading, onTriggerFetch, onTriggerAI }: TaskControlProps) {
  const [fetchLoading, setFetchLoading] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);

  const handleFetch = async () => {
    setFetchLoading(true);
    try {
      await onTriggerFetch();
    } finally {
      setFetchLoading(false);
    }
  };

  const handleAI = async () => {
    setAiLoading(true);
    try {
      await onTriggerAI();
    } finally {
      setAiLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold">任务控制</h2>

      <div className="flex flex-wrap gap-3">
        <button
          onClick={handleFetch}
          disabled={fetchLoading}
          className={cn(
            'flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground',
            'hover:bg-primary/90 disabled:opacity-50'
          )}
        >
          <Zap className={cn('h-4 w-4', fetchLoading && 'animate-pulse')} />
          {fetchLoading ? '采集中...' : '立即采集'}
        </button>
        <button
          onClick={handleAI}
          disabled={aiLoading}
          className={cn(
            'flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2.5 text-sm font-medium',
            'hover:bg-secondary disabled:opacity-50'
          )}
        >
          <Brain className={cn('h-4 w-4', aiLoading && 'animate-pulse')} />
          {aiLoading ? '处理中...' : '立即 AI 处理'}
        </button>
      </div>

      <div>
        <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
          <Activity className="h-4 w-4" />
          <span>最近任务日志</span>
        </div>
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="px-4 py-2 text-left font-medium">任务</th>
                  <th className="px-4 py-2 text-left font-medium">状态</th>
                  <th className="px-4 py-2 text-left font-medium">消息</th>
                  <th className="px-4 py-2 text-right font-medium">时间</th>
                </tr>
              </thead>
              <tbody>
                {isLoading && logs.length === 0 ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <tr key={i} className="border-b border-border last:border-0">
                      <td colSpan={4} className="px-4 py-3">
                        <div className="h-5 animate-pulse rounded bg-muted" />
                      </td>
                    </tr>
                  ))
                ) : logs.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                      暂无任务日志
                    </td>
                  </tr>
                ) : (
                  logs.map((log) => (
                    <tr key={log.id} className="border-b border-border last:border-0 transition-colors hover:bg-muted/30">
                      <td className="px-4 py-3 font-medium">{log.task}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          <StatusIcon status={log.status} />
                          <span className="text-xs capitalize">{log.status}</span>
                        </div>
                      </td>
                      <td className="max-w-xs truncate px-4 py-3 text-muted-foreground">{log.message}</td>
                      <td className="px-4 py-3 text-right text-muted-foreground">
                        {formatRelativeTime(log.created_at)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
