import AdminLayout from '@/components/admin/AdminLayout';
import StatsCards from '@/components/admin/StatsCards';
import SourceTable from '@/components/admin/SourceTable';
import TaskLogTable from '@/components/admin/TaskLogTable';
import { useAdminStats, useTaskLogs } from '@/hooks/useApi';

/**
 * 只读看板：统计 / 来源状态 / 任务日志。
 * 写操作（增删改来源、手动触发采集与 AI 处理）已从页面移除；
 * 后端写接口保留，需带 X-Write-Token 调用，见 docs/api.md。
 */
export default function AdminPage() {
  const { stats, isLoading: statsLoading } = useAdminStats();
  const { logs, isLoading: logsLoading } = useTaskLogs();

  // 使用 stats.sources_health 代替 useSources()，因为它包含 fetched_today
  const sources = stats?.sources_health || [];

  return (
    <AdminLayout>
      <div className="space-y-8">
        <StatsCards stats={stats} isLoading={statsLoading} />

        <SourceTable sources={sources} isLoading={statsLoading} />

        <TaskLogTable logs={logs} isLoading={logsLoading} />
      </div>
    </AdminLayout>
  );
}
