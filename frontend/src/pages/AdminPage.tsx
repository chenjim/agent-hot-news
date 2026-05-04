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
  const { stats, isLoading: statsLoading } = useAdminStats();
  const { sources, isLoading: sourcesLoading, mutate: mutateSources } = useSources();
  const { logs, isLoading: logsLoading, mutate: mutateLogs } = useTaskLogs();

  const handleCreate = async (data: Parameters<typeof createSource>[0]) => {
    await createSource(data);
    await mutateSources();
  };

  const handleTriggerSourceFetch = async (id: number) => {
    await triggerSourceFetch(id);
    await mutateSources();
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
          isLoading={sourcesLoading}
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
