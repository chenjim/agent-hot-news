import { Activity, CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import type { TaskLog } from '@/types';
import { formatRelativeTime } from '@/lib/utils';

interface TaskLogTableProps {
  logs: TaskLog[];
  isLoading: boolean;
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'success') return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
  if (status === 'running') return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />;
  return <XCircle className="h-4 w-4 text-red-500" />;
}

/** 最近任务日志（只读）。触发按钮已移除，任务由调度器与后端写接口驱动。 */
export default function TaskLogTable({ logs, isLoading }: TaskLogTableProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold">任务日志</h2>
        <span className="text-xs text-muted-foreground">只读</span>
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
                    <tr
                      key={log.id}
                      className="border-b border-border last:border-0 transition-colors hover:bg-muted/30"
                    >
                      <td className="px-4 py-3 font-medium">{log.task}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          <StatusIcon status={log.status} />
                          <span className="text-xs capitalize">{log.status}</span>
                        </div>
                      </td>
                      <td className="max-w-xs truncate px-4 py-3 text-muted-foreground">
                        {log.message}
                      </td>
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
