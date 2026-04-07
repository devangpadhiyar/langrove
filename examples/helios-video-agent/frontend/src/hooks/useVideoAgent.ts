import { useCallback, useEffect, useState } from "react";
import { useStream } from "@langchain/langgraph-sdk/react";

export interface ThreadInfo {
  thread_id: string;
  created_at: string;
  metadata?: Record<string, unknown>;
}

function getThreadIdFromUrl(): string | null {
  // URL pattern: /thread/:threadId
  const match = window.location.pathname.match(/^\/thread\/([a-f0-9-]+)/);
  return match ? match[1] : null;
}

function setThreadIdInUrl(id: string | null) {
  const path = id ? `/thread/${id}` : "/";
  window.history.pushState(null, "", path);
}

/**
 * Hook for the Helios video-agent. Wraps the official useStream hook
 * from @langchain/langgraph-sdk/react and adds thread listing + URL sync.
 */
export function useVideoAgent() {
  const [threadId, setThreadIdState] = useState<string | null>(getThreadIdFromUrl);
  const [threads, setThreads] = useState<ThreadInfo[]>([]);

  // Sync threadId to URL whenever it changes
  const setThreadId = useCallback((id: string | null) => {
    setThreadIdState(id);
    setThreadIdInUrl(id);
  }, []);

  // Listen for browser back/forward navigation
  useEffect(() => {
    const onPopState = () => {
      setThreadIdState(getThreadIdFromUrl());
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const [vfsRevision, setVfsRevision] = useState(0);

  const VFS_TOOLS = new Set(["write_file", "edit_file", "delete_file"]);

  const stream = useStream({
    apiUrl: "http://localhost:2024",
    assistantId: "video-agent",
    threadId,
    fetchStateHistory: { limit: 1 },
    reconnectOnMount: true,
    onThreadId: (id: string) => {
      setThreadId(id);
    },
    onUpdateEvent: (data) => {
      // data is { [nodeName]: Partial<State> } — check if any node update
      // contains tool messages from VFS-writing tools
      for (const nodeUpdate of Object.values(data)) {
        const messages = (nodeUpdate as Record<string, unknown>)?.messages;
        if (!Array.isArray(messages)) continue;
        for (const msg of messages) {
          if (
            msg &&
            typeof msg === "object" &&
            (msg as Record<string, unknown>).type === "tool" &&
            VFS_TOOLS.has((msg as Record<string, unknown>).name as string)
          ) {
            setVfsRevision((r) => r + 1);
            return;
          }
        }
      }
    },
  });

  const loadThreads = useCallback(async () => {
    try {
      const result = await stream.client.threads.search();
      setThreads(result as unknown as ThreadInfo[]);
    } catch {
      // Ignore — server may not be running yet
    }
  }, [stream.client]);

  // Load threads on mount and when threadId changes (new thread created)
  useEffect(() => {
    loadThreads();
  }, [loadThreads, threadId]);

  // Auto-join any active background run on this thread (e.g. started in another tab/session)
  useEffect(() => {
    if (!threadId || stream.isLoading) return;
    const stored = sessionStorage.getItem(`lg:stream:${threadId}`);
    if (stored) return; // reconnectOnMount will handle it

    (async () => {
      try {
        const runs = await stream.client.runs.list(threadId, { limit: 1 });
        const active = (runs as Array<{ run_id: string; status: string }>).find(
          (r) => r.status === "pending" || r.status === "running",
        );
        if (active) {
          sessionStorage.setItem(`lg:stream:${threadId}`, active.run_id);
          await (stream as unknown as { joinStream: (runId: string) => Promise<void> }).joinStream(
            active.run_id,
          );
        }
      } catch {
        // Ignore
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  const submitMessage = useCallback(
    async (content: string) => {
      await stream.submit(
        { messages: [{ role: "user", content }] },
        { onDisconnect: "continue", streamResumable: true },
      );
    },
    [stream],
  );

  const approve = useCallback(async () => {
    await stream.submit(null, {
      command: { resume: { decisions: [{ type: "approve" }] } },
      onDisconnect: "continue",
      streamResumable: true,
    });
  }, [stream]);

  const sendFeedback = useCallback(
    async (feedback: string) => {
      await stream.submit(null, {
        command: { resume: { decisions: [{ type: "reject", reason: feedback }] } },
        onDisconnect: "continue",
        streamResumable: true,
      });
    },
    [stream],
  );

  const switchThread = useCallback(
    (id: string | null) => {
      setThreadId(id);
    },
    [setThreadId],
  );

  const newThread = useCallback(() => {
    setThreadId(null);
  }, [setThreadId]);

  return {
    // From useStream
    values: stream.values,
    messages: stream.messages,
    isLoading: stream.isLoading,
    isThreadLoading: stream.isThreadLoading,
    error: stream.error,
    interrupt: stream.interrupt,
    interrupts: stream.interrupts,
    // toolCalls is computed from messages — available on the runtime object
    toolCalls: ((stream as unknown as Record<string, unknown>).toolCalls ?? []) as Array<{
      call: { id: string; name: string; args: Record<string, unknown> };
      result: unknown;
      state: "pending" | "completed" | "error";
    }>,
    stop: stream.stop,
    client: stream.client,
    // Thread management
    threadId,
    threads,
    loadThreads,
    switchThread,
    newThread,
    vfsRevision,
    // Actions
    submitMessage,
    approve,
    sendFeedback,
  };
}
