export interface ToolCallInfo {
  name: string;
  args: Record<string, unknown>;
}

interface Props {
  toolCalls: ToolCallInfo[];
}

const TOOL_LABELS: Record<string, (args: Record<string, unknown>) => string> = {
  write_todos: () => "Storyboarding...",
  write_file: (args) => {
    const path = (args.path || args.file_path || "") as string;
    if (path.includes("/scenes/")) {
      const match = path.match(/scene_(\d+)/);
      return match
        ? `Designing Scene ${parseInt(match[1])}...`
        : "Designing scene...";
    }
    if (path.includes("/styles/")) return "Crafting visual styles...";
    if (path.includes("/scripts/timeline")) return "Orchestrating animation timeline...";
    if (path.includes("/scripts/effects")) return "Building visual effects...";
    if (path.includes("/scripts/")) return "Writing animation code...";
    if (path.includes("/audio/")) return "Configuring audio sync...";
    if (path.includes("/project.json")) return "Setting up project...";
    if (path.includes("/schema.json")) return "Defining template schema...";
    return `Writing ${path}...`;
  },
  edit_file: (args) => {
    const path = (args.path || args.file_path || "") as string;
    if (path.includes("/scenes/")) return "Refining scene...";
    if (path.includes("/scripts/")) return "Adjusting animations...";
    return `Editing ${path}...`;
  },
  read_file: (args) => {
    const path = (args.path || args.file_path || "") as string;
    return `Reading ${path}...`;
  },
  validate_composition: () => "Validating composition structure...",
  assemble_composition: () => "Assembling final composition...",
  generate_input_schema: () => "Generating template schema...",
  get_helios_api_reference: (args) =>
    `Looking up ${(args.topic as string) || "reference"}...`,
  ls: () => "Browsing files...",
  glob: () => "Searching files...",
  grep: () => "Searching content...",
  task: () => "Delegating to sub-agent...",
};

function getToolLabel(tc: ToolCallInfo): string {
  const labelFn = TOOL_LABELS[tc.name];
  if (labelFn) return labelFn(tc.args);
  return `Running ${tc.name}...`;
}

export default function ToolProgress({ toolCalls }: Props) {
  if (toolCalls.length === 0) return null;

  return (
    <div style={styles.container}>
      {toolCalls.map((tc, i) => (
        <div key={tc.name + i} style={styles.item}>
          <span style={styles.spinner}>&#9696;</span>
          <span style={styles.label}>{getToolLabel(tc)}</span>
        </div>
      ))}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: "8px 16px",
    background: "rgba(59, 130, 246, 0.1)",
    borderLeft: "3px solid #3b82f6",
    borderRadius: "4px",
    margin: "8px 0",
  },
  item: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "4px 0",
    fontSize: 13,
    color: "#93c5fd",
  },
  spinner: {
    display: "inline-block",
    animation: "spin 1s linear infinite",
    fontSize: 14,
  },
  label: {
    fontFamily: "monospace",
  },
};
