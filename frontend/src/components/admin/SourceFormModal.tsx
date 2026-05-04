import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import type { Source, SourceFormData } from '@/types';
import { cn } from '@/lib/utils';

interface SourceFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: SourceFormData) => Promise<void>;
  initialData?: Source | null;
}

const emptyForm: SourceFormData = {
  name: '',
  endpoint: '',
};

export default function SourceFormModal({ isOpen, onClose, onSubmit, initialData }: SourceFormModalProps) {
  const [form, setForm] = useState<SourceFormData>(emptyForm);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      if (initialData) {
        setForm({
          name: initialData.name,
          endpoint: initialData.endpoint,
        });
      } else {
        setForm(emptyForm);
      }
    }
  }, [isOpen, initialData]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await onSubmit(form);
      onClose();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold">{initialData ? '编辑来源' : '添加来源'}</h3>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">名称</label>
            <input
              type="text"
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className={cn(
                'w-full rounded-lg border border-input bg-background px-3 py-2 text-sm',
                'focus:outline-none focus:ring-2 focus:ring-ring'
              )}
              placeholder="例如：36氪"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">Endpoint</label>
            <input
              type="url"
              required
              value={form.endpoint}
              onChange={(e) => setForm((f) => ({ ...f, endpoint: e.target.value }))}
              className={cn(
                'w-full rounded-lg border border-input bg-background px-3 py-2 text-sm',
                'focus:outline-none focus:ring-2 focus:ring-ring'
              )}
              placeholder="https://example.com/feed"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-border bg-background px-4 py-2 text-sm font-medium hover:bg-secondary"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={loading}
              className={cn(
                'rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground',
                'hover:bg-primary/90 disabled:opacity-50'
              )}
            >
              {loading ? '保存中...' : '保存'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
