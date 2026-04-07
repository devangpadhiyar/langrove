import { useState } from "react";

interface Props {
  interrupt: unknown;
  onApprove: () => void;
  onFeedback: (feedback: string) => void;
}

export default function ReviewBar({ interrupt, onApprove, onFeedback }: Props) {
  const [feedbackText, setFeedbackText] = useState("");
  const [showFeedbackInput, setShowFeedbackInput] = useState(false);

  if (!interrupt) return null;

  // Extract tool name from DeepAgents HITLRequest structure
  const hitl = interrupt as { value?: { action_requests?: Array<{ name?: string; description?: string }> } };
  const actionRequests = hitl?.value?.action_requests ?? [];
  const toolName = actionRequests[0]?.name ?? "tool";

  const handleFeedback = () => {
    if (feedbackText.trim()) {
      onFeedback(feedbackText.trim());
      setFeedbackText("");
      setShowFeedbackInput(false);
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <span style={styles.icon}>&#9881;</span>
        <span>Approve <code style={styles.toolCode}>{toolName}</code>?</span>
      </div>

      {!showFeedbackInput ? (
        <div style={styles.actions}>
          <button style={styles.approveBtn} onClick={onApprove}>
            Approve
          </button>
          <button
            style={styles.feedbackBtn}
            onClick={() => setShowFeedbackInput(true)}
          >
            Reject
          </button>
        </div>
      ) : (
        <div style={styles.feedbackContainer}>
          <textarea
            style={styles.textarea}
            value={feedbackText}
            onChange={(e) => setFeedbackText(e.target.value)}
            placeholder="Reason for rejection... (e.g., 'Make the product reveal more dramatic')"
            rows={3}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleFeedback();
              }
            }}
          />
          <div style={styles.feedbackActions}>
            <button style={styles.sendBtn} onClick={handleFeedback}>
              Send Feedback
            </button>
            <button
              style={styles.cancelBtn}
              onClick={() => {
                setShowFeedbackInput(false);
                setFeedbackText("");
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    background: "rgba(234, 179, 8, 0.1)",
    border: "1px solid rgba(234, 179, 8, 0.3)",
    borderRadius: 8,
    padding: 16,
    margin: "12px 0",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    fontSize: 14,
    fontWeight: 600,
    color: "#fbbf24",
    marginBottom: 12,
  },
  icon: { fontSize: 16 },
  toolCode: {
    fontFamily: "monospace",
    fontSize: 13,
    background: "rgba(251, 191, 36, 0.15)",
    padding: "1px 5px",
    borderRadius: 3,
  },
  actions: { display: "flex", gap: 8 },
  approveBtn: {
    background: "#22c55e",
    color: "#000",
    border: "none",
    borderRadius: 6,
    padding: "8px 20px",
    fontSize: 14,
    fontWeight: 600,
    cursor: "pointer",
  },
  feedbackBtn: {
    background: "transparent",
    color: "#fbbf24",
    border: "1px solid rgba(234, 179, 8, 0.4)",
    borderRadius: 6,
    padding: "8px 20px",
    fontSize: 14,
    cursor: "pointer",
  },
  feedbackContainer: { display: "flex", flexDirection: "column" as const, gap: 8 },
  textarea: {
    width: "100%",
    background: "rgba(0, 0, 0, 0.3)",
    color: "#e0e0e0",
    border: "1px solid rgba(255, 255, 255, 0.1)",
    borderRadius: 6,
    padding: 10,
    fontSize: 13,
    fontFamily: "inherit",
    resize: "vertical" as const,
  },
  feedbackActions: { display: "flex", gap: 8 },
  sendBtn: {
    background: "#3b82f6",
    color: "#fff",
    border: "none",
    borderRadius: 6,
    padding: "8px 16px",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
  },
  cancelBtn: {
    background: "transparent",
    color: "#888",
    border: "1px solid rgba(255, 255, 255, 0.1)",
    borderRadius: 6,
    padding: "8px 16px",
    fontSize: 13,
    cursor: "pointer",
  },
};
