import AdminLayout from '@/components/admin/AdminLayout';
import StatsCards from '@/components/admin/StatsCards';
import SourceTable from '@/components/admin/SourceTable';
import TaskControl from '@/components/admin/TaskControl';
import {
  useAdminStats,
  useSources,
  useTaskLogs,
  createSource,
  triggerFetch,
  triggerAI,
  triggerSourceFetch,
} from '@/hooks/useApi';

export default function AdminPage() {
  const { stats, isLoading: statsLoading, mutate: mutateStats } = useAdminStats();
  const { logs, isLoading: logsLoading, mutate: mutateLogs } = useTaskLogs();

  // 使用 stats.sources_health 代替 useSources()，因为它包含 fetched_today
  const sources = stats?.sources_health || [];

  const handleCreate = async (data: Parameters<typeof createSource>[0]) => {
    await createSource(data);
    await mutateStats();
  };

  const handleTriggerSourceFetch = async (id: number) => {
    await triggerSourceFetch(id);
    await mutateStats();
  };

  const handleTriggerFetch = async () => {
    await triggerFetch();
    await mutateLogs();
  };

  const handleTriggerAI = async () => {
    await triggerAI();
    await mutateLogs();
  };

  return (
    <AdminLayout>
      <div className="space-y-8">
        <StatsCards stats={stats} isLoading={statsLoading} />

        <SourceTable
          sources={sources}
          isLoading={statsLoading}
          onCreate={handleCreate}
          onTriggerFetch={handleTriggerSourceFetch}
        />

        <TaskControl
          logs={logs}
          isLoading={logsLoading}
          onTriggerFetch={handleTriggerFetch}
          onTriggerAI={handleTriggerAI}
        />
      </div>
    </AdminLayout>
  );
}
