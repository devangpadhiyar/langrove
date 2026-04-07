import { useRef, useState, useEffect } from "react";
import ToolProgress from "./ToolProgress";
import type { ToolCallInfo } from "./ToolProgress";
import ReviewBar from "./ReviewBar";

interface ToolCallWithResult {
  call: { id: string; name: string; args: Record<string, unknown> };
  result: unknown;
  state: "pending" | "completed" | "error";
}

interface MessageLike {
  id?: string;
  type?: string;
  content?: string | Array<{ type: string; text?: string }>;
  tool_calls?: Array<{ name: string; args: Record<string, unknown> }>;
}

interface Props {
  messages: MessageLike[];
  isLoading: boolean;
  interrupt: unknown;
  toolCalls: ToolCallWithResult[];
  onSubmit: (content: string) => void;
  onStop: () => void;
  onApprove: () => void;
  onFeedback: (feedback: string) => void;
}

function getMessageContent(msg: MessageLike): string {
  if (typeof msg.content === "string") return msg.content;
  if (Array.isArray(msg.content)) {
    return msg.content
      .filter((c) => c.type === "text" && c.text)
      .map((c) => c.text)
      .join("");
  }
  return "";
}

function getMessageRole(msg: MessageLike): "user" | "assistant" | "tool" {
  if (msg.type === "human") return "user";
  if (msg.type === "tool") return "tool";
  return "assistant";
}

export default function ChatPanel({
  messages,
  isLoading,
  interrupt,
  toolCalls,
  onSubmit,
  onStop,
  onApprove,
  onFeedback,
}: Props) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Pending tool calls for the progress indicator
  const pendingTools: ToolCallInfo[] = (toolCalls ?? [])
    .filter((tc) => tc.state === "pending")
    .map((tc) => ({ name: tc.call.name, args: tc.call.args }));

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pendingTools.length]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    onSubmit(trimmed);
    setInput("");
  };

  // Filter out tool messages for display
  const displayMessages = messages.filter((m) => getMessageRole(m) !== "tool");

  return (
    <div style={styles.container}>
      {/* Messages */}
      <div style={styles.messages}>
        {displayMessages.length === 0 && !isLoading && (
          <div style={styles.empty}>
            <h2 style={styles.emptyTitle}>Helios Video Agent</h2>
            <p style={styles.emptyText}>
              Describe the video you want to create. Be specific about mood,
              style, duration, content, and audience.
            </p>
            <div style={styles.examples}>
              <p style={styles.exampleLabel}>Example prompts:</p>
              <p style={styles.example}>
                &quot;Create a 15-second product ad for wireless headphones. Dark
                cinematic theme, electric blue accents, particle effects.&quot;
              </p>
              <p style={styles.example}>
                &quot;Design a 30-second startup pitch video. Clean white
                background, bold typography, data viz animations.&quot;
              </p>
              <p style={styles.example}>
                &quot;Make a 10-second Instagram story for a coffee brand. Warm
                tones, steam particles, kinetic text.&quot;
              </p>
            </div>
          </div>
        )}

        {displayMessages.map((msg, i) => {
          const role = getMessageRole(msg);
          const content = getMessageContent(msg);

          // Show tool calls on AI messages that have them — match by ID, not name
          const msgToolCalls = (msg.tool_calls ?? []) as Array<{ id?: string; name: string; args: Record<string, unknown> }>;
          const hasToolCalls = role === "assistant" && msgToolCalls.length > 0;

          // Find completed tool results for this message's tool calls (by ID)
          const completedTools = hasToolCalls
            ? (toolCalls ?? []).filter(
                (tc) =>
                  tc.state === "completed" &&
                  msgToolCalls.some((mtc) => mtc.id && mtc.id === tc.call.id),
              )
            : [];

          return (
            <div key={msg.id || i}>
              {/* Message bubble (only if has content) */}
              {content && (
                <div
                  style={{
                    ...styles.message,
                    ...(role === "user" ? styles.userMsg : styles.assistantMsg),
                  }}
                >
                  <div style={styles.msgRole}>
                    {role === "user" ? "You" : "Creative Director"}
                  </div>
                  <div style={styles.msgContent}>
                    {content.split("\n").map((line, j) => (
                      <p key={j} style={styles.msgLine}>
                        {line}
                      </p>
                    ))}
                  </div>
                </div>
              )}

              {/* Show completed tool calls inline after the AI message */}
              {completedTools.length > 0 && (
                <div style={styles.completedTools}>
                  {completedTools.map((tc) => (
                    <div key={tc.call.id} style={styles.completedTool}>
                      <span style={styles.checkmark}>&#10003;</span>
                      <span style={styles.toolName}>
                        {getToolLabel(tc.call.name, tc.call.args)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {/* Show pending tool calls as active progress */}
        <ToolProgress toolCalls={pendingTools} />

        <ReviewBar
          interrupt={interrupt}
          onApprove={onApprove}
          onFeedback={onFeedback}
        />

        {isLoading && pendingTools.length === 0 && (
          <div style={styles.thinking}>Thinking...</div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} style={styles.inputArea}>
        <input
          style={styles.input}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={isLoading ? "Agent is working..." : "Describe your video..."}
          disabled={isLoading}
        />
        {isLoading ? (
          <button
            type="button"
            style={styles.stopBtn}
            onClick={onStop}
          >
            Stop
          </button>
        ) : (
          <button
            type="submit"
            style={{
              ...styles.sendBtn,
              opacity: !input.trim() ? 0.4 : 1,
            }}
            disabled={!input.trim()}
          >
            Send
          </button>
        )}
      </form>
    </div>
  );
}

const TOOL_LABELS: Record<string, (args: Record<string, unknown>) => string> = {
  write_todos: () => "Planned storyboard",
  write_file: (args) => {
    const path = (args.path || args.file_path || "") as string;
    if (path.includes("/scenes/")) return `Designed scene: ${path.split("/").pop()}`;
    if (path.includes("/styles/")) return `Created styles: ${path.split("/").pop()}`;
    if (path.includes("/scripts/")) return `Wrote script: ${path.split("/").pop()}`;
    if (path.includes("/audio/")) return "Configured audio";
    if (path.includes("/project.json")) return "Set up project";
    return `Wrote ${path}`;
  },
  edit_file: (args) => {
    const path = (args.path || args.file_path || "") as string;
    return `Edited ${path.split("/").pop() || path}`;
  },
  read_file: (args) => `Read ${((args.path || args.file_path || "") as string).split("/").pop()}`,
  validate_composition: () => "Validated composition",
  assemble_composition: () => "Assembled final composition",
  generate_input_schema: () => "Generated template schema",
  get_helios_api_reference: (args) => `Looked up ${(args.topic as string) || "reference"}`,
};

function getToolLabel(name: string, args: Record<string, unknown>): string {
  const labelFn = TOOL_LABELS[name];
  if (labelFn) return labelFn(args);
  return `Ran ${name}`;
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    borderRight: "1px solid rgba(255, 255, 255, 0.06)",
  },
  messages: { flex: 1, overflowY: "auto", padding: 16 },
  empty: { padding: "40px 20px", textAlign: "center" },
  emptyTitle: { fontSize: 22, fontWeight: 700, color: "#fff", marginBottom: 8 },
  emptyText: { fontSize: 14, color: "#888", marginBottom: 24, lineHeight: 1.5 },
  examples: { textAlign: "left", maxWidth: 400, margin: "0 auto" },
  exampleLabel: {
    fontSize: 12,
    color: "#666",
    marginBottom: 8,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  example: {
    fontSize: 13,
    color: "#555",
    padding: "8px 12px",
    background: "rgba(255, 255, 255, 0.03)",
    borderRadius: 6,
    marginBottom: 6,
    lineHeight: 1.4,
    fontStyle: "italic",
  },
  message: { marginBottom: 12, padding: 12, borderRadius: 8 },
  userMsg: {
    background: "rgba(59, 130, 246, 0.1)",
    borderLeft: "3px solid #3b82f6",
  },
  assistantMsg: {
    background: "rgba(255, 255, 255, 0.03)",
    borderLeft: "3px solid #444",
  },
  msgRole: {
    fontSize: 11,
    fontWeight: 600,
    color: "#888",
    marginBottom: 4,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  msgContent: {},
  msgLine: { fontSize: 14, lineHeight: 1.5, color: "#d0d0d0", marginBottom: 2 },
  completedTools: {
    padding: "4px 16px",
    marginBottom: 8,
  },
  completedTool: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "3px 0",
    fontSize: 12,
    color: "#6b7280",
  },
  checkmark: {
    color: "#22c55e",
    fontSize: 11,
  },
  toolName: {
    fontFamily: "monospace",
    fontSize: 11,
  },
  thinking: { fontSize: 13, color: "#666", fontStyle: "italic", padding: "8px 0" },
  inputArea: {
    display: "flex",
    gap: 8,
    padding: 12,
    borderTop: "1px solid rgba(255, 255, 255, 0.06)",
    background: "rgba(0, 0, 0, 0.3)",
  },
  input: {
    flex: 1,
    background: "rgba(255, 255, 255, 0.06)",
    color: "#e0e0e0",
    border: "1px solid rgba(255, 255, 255, 0.1)",
    borderRadius: 8,
    padding: "10px 14px",
    fontSize: 14,
    outline: "none",
  },
  sendBtn: {
    background: "#3b82f6",
    color: "#fff",
    border: "none",
    borderRadius: 8,
    padding: "10px 20px",
    fontSize: 14,
    fontWeight: 600,
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  stopBtn: {
    background: "#ef4444",
    color: "#fff",
    border: "none",
    borderRadius: 8,
    padding: "10px 20px",
    fontSize: 14,
    fontWeight: 600,
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
};
