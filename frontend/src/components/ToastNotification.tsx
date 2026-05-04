import { useEffect, useState } from 'react';
import { X, Flame } from 'lucide-react';
import type { HotEvent } from '@/types';
import { cn } from '@/lib/utils';

interface Toast {
  id: string;
  event: HotEvent;
}

let toastId = 0;
const listeners: Set<(toasts: Toast[]) => void> = new Set();
let toasts: Toast[] = [];

function notifyListeners() {
  listeners.forEach((fn) => fn([...toasts]));
}

export function pushToast(event: HotEvent) {
  const id = `${Date.now()}-${toastId++}`;
  toasts = [...toasts, { id, event }];
  notifyListeners();

  setTimeout(() => {
    toasts = toasts.filter((t) => t.id !== id);
    notifyListeners();
  }, 3000);
}

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), 50);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div
      className={cn(
        'flex w-80 items-start gap-3 rounded-xl border border-border bg-card p-4 shadow-lg transition-all duration-300',
        visible ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0'
      )}
    >
      <div className="mt-0.5 rounded-full bg-orange-500/10 p-1.5">
        <Flame className="h-4 w-4 text-orange-500" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold">新热点事件</p>
        <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{toast.event.title}</p>
        {toast.event.summary && (
          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{toast.event.summary}</p>
        )}
      </div>
      <button
        onClick={onDismiss}
        className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export default function ToastNotification() {
  const [items, setItems] = useState<Toast[]>([]);

  useEffect(() => {
    listeners.add(setItems);
    return () => {
      listeners.delete(setItems);
    };
  }, []);

  const dismiss = (id: string) => {
    toasts = toasts.filter((t) => t.id !== id);
    notifyListeners();
  };

  if (items.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
      {items.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={() => dismiss(toast.id)} />
      ))}
    </div>
  );
}
