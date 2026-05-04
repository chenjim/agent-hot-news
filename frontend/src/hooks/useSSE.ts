import { useEffect, useRef, useCallback } from 'react';
import { globalMutate } from '@/hooks/useApi';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:51180/api/v1';

interface UseSSEOptions {
  onMessage?: (data: unknown) => void;
  onError?: (error: Event) => void;
}

export function useSSE(url: string, options: UseSSEOptions = {}) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const connect = useCallback(() => {
    if (eventSourceRef.current?.readyState === EventSource.OPEN) {
      return;
    }

    try {
      const fullUrl = url.startsWith('http') ? url : `${API_BASE}${url}`;
      const es = new EventSource(fullUrl);
      eventSourceRef.current = es;

      es.onopen = () => {
        reconnectAttemptsRef.current = 0;
      };

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          optionsRef.current.onMessage?.(data);
        } catch {
          optionsRef.current.onMessage?.(event.data);
        }
      };

      es.onerror = (error) => {
        optionsRef.current.onError?.(error);
        es.close();

        // Exponential backoff reconnect
        const maxDelay = 30000;
        const baseDelay = 1000;
        const delay = Math.min(baseDelay * Math.pow(2, reconnectAttemptsRef.current), maxDelay);
        reconnectAttemptsRef.current += 1;

        if (reconnectTimerRef.current) {
          clearTimeout(reconnectTimerRef.current);
        }
        reconnectTimerRef.current = setTimeout(() => {
          connect();
        }, delay);
      };
    } catch {
      // Silent fail
    }
  }, [url]);

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  useEffect(() => {
    connect();
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);
}

export function useHotEventsSSE(onMessage?: (data: unknown) => void) {
  useSSE('/sse/hot-events', {
    onMessage: (data) => {
      // Refresh hot events list via SWR mutate
      globalMutate((key) => typeof key === 'string' && key.includes('/hot-events'));
      onMessage?.(data);
    },
  });
}
