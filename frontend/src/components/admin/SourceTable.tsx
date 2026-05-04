import { useState } from 'react';
import { Plus, Pencil, Trash2, Play, AlertCircle, CheckCircle2, PauseCircle } from 'lucide-react';
import type { Source, SourceFormData } from '@/types';
import { cn, formatRelativeTime } from '@/lib/utils';
import SourceFormModal from './SourceFormModal';

interface SourceTableProps {
  sources: Source[];
  isLoading: boolean;
  onCreate: (data: SourceFormData) => Promise<void>;
  onUpdate: (id: number, data: SourceFormData) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
  onTriggerFetch: (id: number) => Promise<void>;
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

export default function SourceTable({
  sources,
  isLoading,
  onCreate,
  onUpdate,
  onDelete,
  onTriggerFetch,
}: SourceTableProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Source | null>(null);
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const handleEdit = (source: Source) => {
    setEditing(source);
    setModalOpen(true);
  };

  const handleCreate = () => {
    setEditing(null);
    setModalOpen(true);
  };

  const handleSubmit = async (data: SourceFormData) => {
    if (editing) {
      await onUpdate(editing.id, data);
    } else {
      await onCreate(data);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除该来源吗？')) return;
    setActionLoading(id);
    try {
      await onDelete(id);
    } finally {
      setActionLoading(null);
    }
  };

  const handleTrigger = async (id: number) => {
    setActionLoading(id);
    try {
      await onTriggerFetch(id);
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold">来源管理</h2>
        <button
          onClick={handleCreate}
          className={cn(
            'flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground',
            'hover:bg-primary/90'
          )}
        >
          <Plus className="h-4 w-4" />
          添加来源
        </button>
      </div>

      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="px-4 py-3 text-left font-medium">名称</th>
                <th className="px-4 py-3 text-left font-medium">状态</th>
                <th className="px-4 py-3 text-left font-medium">最后采集</th>
                <th className="px-4 py-3 text-right font-medium">操作</th>
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
                  <tr key={source.id} className="border-b border-border last:border-0 transition-colors hover:bg-muted/30">
                    <td className="px-4 py-3 font-medium">{source.name}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={source.status} />
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {formatRelativeTime(source.last_fetched_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => handleTrigger(source.id)}
                          disabled={actionLoading === source.id}
                          title="手动采集"
                          className="rounded p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground disabled:opacity-50"
                        >
                          <Play className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleEdit(source)}
                          title="编辑"
                          className="rounded p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(source.id)}
                          disabled={actionLoading === source.id}
                          title="删除"
                          className="rounded p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <SourceFormModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onSubmit={handleSubmit}
        initialData={editing}
      />
    </div>
  );
}
