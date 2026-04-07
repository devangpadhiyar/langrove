import ChatPanel from "./components/ChatPanel";
import PreviewPanel from "./components/PreviewPanel";
import { useVideoAgent } from "./hooks/useVideoAgent";
import type { ThreadInfo } from "./hooks/useVideoAgent";

export default function App() {
  const {
    values,
    messages,
    isLoading,
    interrupt,
    toolCalls,
    threadId,
    threads,
    stop,
    submitMessage,
    approve,
    sendFeedback,
    switchThread,
    newThread,
    vfsRevision,
  } = useVideoAgent();

  const todos = ((values as Record<string, unknown>)?.todos ?? []) as Array<{
    content: string;
    status: string;
  }>;

  return (
    <div style={styles.layout}>
      {/* Thread Sidebar */}
      <div style={styles.sidebar}>
        <div style={styles.sidebarHeader}>
          <h2 style={styles.sidebarTitle}>Threads</h2>
          <button style={styles.newBtn} onClick={newThread}>
            + New
          </button>
        </div>
        <div style={styles.threadList}>
          {threads.length === 0 && (
            <p style={styles.noThreads}>No threads yet</p>
          )}
          {threads.map((t: ThreadInfo) => (
            <button
              key={t.thread_id}
              style={{
                ...styles.threadItem,
                ...(t.thread_id === threadId ? styles.threadItemActive : {}),
              }}
              onClick={() => switchThread(t.thread_id)}
            >
              <span style={styles.threadId}>
                {t.thread_id.slice(0, 8)}...
              </span>
              <span style={styles.threadDate}>
                {new Date(t.created_at).toLocaleDateString()}
              </span>
            </button>
          ))}
        </div>

        {/* Todos */}
        {todos.length > 0 && (
          <div style={styles.todosSection}>
            <h3 style={styles.todosTitle}>Storyboard</h3>
            {todos.map((t, i) => (
              <div key={i} style={styles.todoItem}>
                <span style={styles.todoIcon}>
                  {t.status === "completed" ? "✓" : t.status === "in_progress" ? "◠" : "○"}
                </span>
                <span style={{
                  ...styles.todoText,
                  ...(t.status === "completed" ? styles.todoCompleted : {}),
                  ...(t.status === "in_progress" ? styles.todoActive : {}),
                }}>
                  {t.content}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Chat Panel */}
      <div style={styles.chatPanel}>
        <ChatPanel
          messages={messages}
          isLoading={isLoading}
          interrupt={interrupt}
          toolCalls={toolCalls}
          onSubmit={submitMessage}
          onStop={stop}
          onApprove={approve}
          onFeedback={sendFeedback}
        />
      </div>

      {/* Preview Panel */}
      <div style={styles.previewPanel}>
        <PreviewPanel
          threadId={threadId}
          interrupt={interrupt}
          isLoading={isLoading}
          vfsRevision={vfsRevision}
        />
      </div>

      {/* Global animations */}
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        @keyframes gradientShift {
          0% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }
      `}</style>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  layout: {
    display: "flex",
    height: "100vh",
    width: "100vw",
    overflow: "hidden",
    background: "#0a0a0a",
  },
  sidebar: {
    width: 220,
    minWidth: 180,
    height: "100%",
    borderRight: "1px solid rgba(255, 255, 255, 0.06)",
    display: "flex",
    flexDirection: "column",
    background: "#050505",
  },
  sidebarHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "12px 14px",
    borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
  },
  sidebarTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: "#888",
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  newBtn: {
    background: "rgba(59, 130, 246, 0.15)",
    color: "#93c5fd",
    border: "1px solid rgba(59, 130, 246, 0.3)",
    borderRadius: 4,
    padding: "4px 10px",
    fontSize: 12,
    cursor: "pointer",
    fontWeight: 600,
  },
  threadList: {
    flex: 1,
    overflowY: "auto",
    padding: "8px 8px",
  },
  noThreads: {
    fontSize: 12,
    color: "#555",
    textAlign: "center",
    padding: "20px 0",
  },
  threadItem: {
    display: "flex",
    flexDirection: "column",
    width: "100%",
    background: "transparent",
    border: "1px solid transparent",
    borderRadius: 6,
    padding: "8px 10px",
    marginBottom: 4,
    cursor: "pointer",
    textAlign: "left",
    color: "#999",
    transition: "background 0.15s",
  },
  threadItemActive: {
    background: "rgba(59, 130, 246, 0.1)",
    borderColor: "rgba(59, 130, 246, 0.3)",
    color: "#d0d0d0",
  },
  threadId: {
    fontSize: 12,
    fontFamily: "monospace",
  },
  threadDate: {
    fontSize: 10,
    color: "#555",
    marginTop: 2,
  },
  chatPanel: {
    width: "35%",
    minWidth: 320,
    maxWidth: 480,
    height: "100%",
  },
  previewPanel: {
    flex: 1,
    height: "100%",
  },
  todosSection: {
    borderTop: "1px solid rgba(255, 255, 255, 0.06)",
    padding: "10px 12px",
    overflowY: "auto",
  },
  todosTitle: {
    fontSize: 11,
    fontWeight: 600,
    color: "#666",
    textTransform: "uppercase",
    letterSpacing: 1,
    marginBottom: 8,
  },
  todoItem: {
    display: "flex",
    alignItems: "flex-start",
    gap: 6,
    padding: "3px 0",
  },
  todoIcon: {
    fontSize: 11,
    flexShrink: 0,
    marginTop: 1,
    color: "#555",
  },
  todoText: {
    fontSize: 11,
    lineHeight: 1.4,
    color: "#555",
  },
  todoCompleted: {
    color: "#22c55e",
    textDecoration: "line-through" as const,
  },
  todoActive: {
    color: "#93c5fd",
  },
};
