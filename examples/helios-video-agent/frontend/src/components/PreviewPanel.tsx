import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchComposition,
  fetchCompositionMetadata,
  fetchFile,
  getVfsUrl,
  listVfsFiles,
} from "../lib/store";
import type { CompositionMetadata, VfsFile } from "../lib/store";

interface Props {
  threadId: string | null;
  interrupt: unknown;
  isLoading: boolean;
  vfsRevision: number;
}

type Tab = "files" | "preview";

export default function PreviewPanel({ threadId, interrupt, isLoading, vfsRevision }: Props) {
  const [tab, setTab] = useState<Tab>("files");
  const [compositionHtml, setCompositionHtml] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<CompositionMetadata | null>(null);
  const [files, setFiles] = useState<VfsFile[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [isFetching, setIsFetching] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState(0);

  const loadFiles = useCallback(async () => {
    if (!threadId) return;
    const result = await listVfsFiles(threadId);
    setFiles(result);
  }, [threadId]);

  const loadComposition = useCallback(async () => {
    if (!threadId) return;
    setIsFetching(true);
    const [html, meta] = await Promise.all([
      fetchComposition(threadId),
      fetchCompositionMetadata(threadId),
    ]);
    if (html) setCompositionHtml(html);
    if (meta) setMetadata(meta);
    setIsFetching(false);
  }, [threadId]);

  const loadFileContent = useCallback(
    async (filePath: string) => {
      if (!threadId) return;
      setSelectedFile(filePath);
      const content = await fetchFile(threadId, filePath);
      setFileContent(content);
    },
    [threadId],
  );

  // Load files on mount, when loading stops, or when a VFS tool call completes
  useEffect(() => {
    loadFiles();
  }, [loadFiles, isLoading, vfsRevision]);

  // Auto-fetch composition when interrupted
  useEffect(() => {
    if (interrupt && threadId) {
      loadComposition();
      loadFiles();
      setTab("preview");
    }
  }, [interrupt, threadId, loadComposition, loadFiles]);

  // Clear state when thread changes
  useEffect(() => {
    setCompositionHtml(null);
    setMetadata(null);
    setFiles([]);
    setSelectedFile(null);
    setFileContent(null);
    setTab("files");
  }, [threadId]);

  const handleExport = async () => {
    if (!threadId || isExporting) return;
    setIsExporting(true);
    setExportProgress(0);

    const w = compDims?.width ?? 1920;
    const h = compDims?.height ?? 1080;

    // Use the same-origin VFS URL so the player can access the iframe's
    // contentWindow (Direct Mode) for export.
    const compositionUrl = getVfsUrl(threadId, "composition.html");

    const player = document.createElement("helios-player") as any;
    player.style.position = "fixed";
    player.style.left = "-9999px";
    player.style.width = `${w}px`;
    player.style.height = `${h}px`;
    document.body.appendChild(player);

    try {
      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(
          () => reject(new Error("Player connection timed out")),
          30000
        );
        player.addEventListener(
          "canplay",
          () => { clearTimeout(timeout); resolve(); },
          { once: true }
        );
        player.addEventListener(
          "error",
          () => { clearTimeout(timeout); reject(new Error("Player failed to load")); },
          { once: true }
        );
        player.src = compositionUrl;
      });

      // Use canvas mode — captures the <canvas> element directly via
      // WebCodecs. DOM mode fails for compositions with external resources
      // (fonts, CDN scripts) due to canvas tainting / SVG serialization.
      // For full-quality rendering with all DOM elements, use the CLI:
      //   npx helios render ./composition.html -o output.mp4
      await player.export({
        format: "mp4" as const,
        mode: "canvas" as const,
        width: w,
        height: h,
        onProgress: (p: number) => setExportProgress(p),
      });
    } catch (err) {
      console.error("Export failed:", err);
      alert(
        "Client-side export failed.\n\n" +
        "For full-quality rendering, use the Helios CLI:\n" +
        "  npx helios render ./composition.html -o output.mp4"
      );
    } finally {
      document.body.removeChild(player);
      setIsExporting(false);
    }
  };

  const handleDownload = () => {
    if (!compositionHtml) return;
    const blob = new Blob([compositionHtml], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "composition.html";
    a.click();
    URL.revokeObjectURL(url);
  };

  // Get composition dimensions from metadata, falling back to HTML parsing
  const compDims = useMemo(() => {
    if (metadata) return { width: metadata.width, height: metadata.height };
    if (!compositionHtml) return null;
    // Fallback: parse from new Helios({ width: N, height: N }) or data-width
    const wMatch = compositionHtml.match(/width:\s*(\d+)/) ?? compositionHtml.match(/data-width="(\d+)"/);
    const hMatch = compositionHtml.match(/height:\s*(\d+)/) ?? compositionHtml.match(/data-height="(\d+)"/);
    return wMatch && hMatch ? { width: parseInt(wMatch[1]), height: parseInt(hMatch[1]) } : null;
  }, [metadata, compositionHtml]);

  // Measure preview container for scale-to-fit
  const previewRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = previewRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      setContainerSize({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [tab]);

  // Scale with 8px padding on each side
  const pad = 16;
  const scale =
    compDims && containerSize.width > pad * 2
      ? Math.min(
          (containerSize.width - pad * 2) / compDims.width,
          (containerSize.height - pad * 2) / compDims.height,
        )
      : 1;

  // Sort files by path
  const sortedFiles = [...files].sort((a, b) => a.key.localeCompare(b.key));

  return (
    <div style={styles.container}>
      {/* Tab Header */}
      <div style={styles.header}>
        <div style={styles.tabs}>
          <button
            style={{ ...styles.tab, ...(tab === "files" ? styles.tabActive : {}) }}
            onClick={() => setTab("files")}
          >
            Files {files.length > 0 && `(${files.length})`}
          </button>
          <button
            style={{ ...styles.tab, ...(tab === "preview" ? styles.tabActive : {}) }}
            onClick={() => { setTab("preview"); loadComposition(); }}
          >
            Preview
          </button>
        </div>
        <div style={styles.headerActions}>
          {tab === "files" && threadId && (
            <button style={styles.refreshBtn} onClick={loadFiles}>
              Refresh
            </button>
          )}
          {tab === "preview" && compositionHtml && (
            <>
              <button style={styles.downloadBtn} onClick={handleDownload}>
                Download HTML
              </button>
              <button
                style={{
                  ...styles.exportBtn,
                  ...(isExporting ? styles.exportBtnDisabled : {}),
                }}
                onClick={handleExport}
                disabled={isExporting}
              >
                {isExporting
                  ? `Exporting ${Math.round(exportProgress * 100)}%`
                  : "Quick Export"}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Files Tab */}
      {tab === "files" && (
        <div style={styles.filesLayout}>
          {/* File Tree */}
          <div style={styles.fileTree}>
            {sortedFiles.length === 0 && !isLoading && (
              <p style={styles.noFiles}>No files yet</p>
            )}
            {sortedFiles.length === 0 && isLoading && (
              <p style={styles.noFiles}>Agent is writing files...</p>
            )}
            {sortedFiles.map((f) => (
              <button
                key={f.key}
                style={{
                  ...styles.fileItem,
                  ...(selectedFile === f.key ? styles.fileItemActive : {}),
                }}
                onClick={() => loadFileContent(f.key)}
              >
                <span style={styles.fileIcon}>
                  {getFileIcon(f.key)}
                </span>
                <span style={styles.fileName}>{f.key}</span>
              </button>
            ))}
          </div>

          {/* File Content Viewer */}
          <div style={styles.fileViewer}>
            {selectedFile && fileContent !== null ? (
              <>
                <div style={styles.fileViewerHeader}>
                  <span style={styles.fileViewerPath}>{selectedFile}</span>
                  <span style={styles.fileViewerSize}>
                    {fileContent.length} chars
                  </span>
                </div>
                <pre style={styles.fileViewerContent}>{fileContent}</pre>
              </>
            ) : selectedFile ? (
              <div style={styles.fileViewerEmpty}>Loading...</div>
            ) : (
              <div style={styles.fileViewerEmpty}>
                Select a file to view its contents
              </div>
            )}
          </div>
        </div>
      )}

      {/* Preview Tab */}
      {tab === "preview" && (
        <div ref={previewRef} style={styles.previewArea}>
          {compositionHtml && threadId ? (
            compDims ? (
              <div
                style={{
                  width: Math.floor(compDims.width * scale),
                  height: Math.floor(compDims.height * scale),
                  overflow: "hidden",
                  flexShrink: 0,
                }}
              >
                <iframe
                  key={vfsRevision}
                  style={{
                    width: compDims.width,
                    height: compDims.height,
                    border: "none",
                    background: "#000",
                    transform: `scale(${scale})`,
                    transformOrigin: "top left",
                    display: "block",
                  }}
                  src={getVfsUrl(threadId, "composition.html")}
                  sandbox="allow-scripts allow-same-origin"
                  title="Composition Preview"
                />
              </div>
            ) : (
              <iframe
                key={vfsRevision}
                style={styles.iframe}
                src={getVfsUrl(threadId, "composition.html")}
                sandbox="allow-scripts allow-same-origin"
                title="Composition Preview"
              />
            )
          ) : isFetching ? (
            <div style={styles.placeholder}>
              <div style={styles.loadingSpinner} />
              <p style={{ color: "#666" }}>Loading composition...</p>
            </div>
          ) : isLoading ? (
            <div style={styles.placeholder}>
              <div style={styles.animatedBg} />
              <div style={styles.placeholderContent}>
                <p style={styles.placeholderTitle}>Creating your video...</p>
                <p style={styles.placeholderText}>
                  Preview will appear when the composition is assembled.
                </p>
              </div>
            </div>
          ) : (
            <div style={styles.placeholder}>
              <div style={styles.placeholderContent}>
                <p style={styles.placeholderTitle}>No composition yet</p>
                <p style={styles.placeholderText}>
                  The agent needs to call assemble_composition() to generate a preview.
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Export progress overlay */}
      {tab === "preview" && isExporting && (
        <div style={styles.exportOverlay}>
          <div style={styles.exportProgressTrack}>
            <div
              style={{
                ...styles.exportProgressBar,
                width: `${Math.round(exportProgress * 100)}%`,
              }}
            />
          </div>
          <p style={styles.exportText}>
            Rendering video... {Math.round(exportProgress * 100)}%
          </p>
        </div>
      )}

      {/* Render instructions */}
      {tab === "preview" && compositionHtml && !isExporting && (
        <div style={styles.renderInfo}>
          <p style={styles.renderText}>
            Render:{" "}
            <code style={styles.code}>
              npx helios render composition.html -o output.mp4
            </code>
          </p>
        </div>
      )}
    </div>
  );
}

function getFileIcon(path: string): string {
  if (path.endsWith(".html")) return "\u{1F310}";
  if (path.endsWith(".css")) return "\u{1F3A8}";
  if (path.endsWith(".js")) return "\u26A1";
  if (path.endsWith(".json")) return "\u{1F4CB}";
  if (path.endsWith(".py")) return "\u{1F40D}";
  if (path.endsWith(".md")) return "\u{1F4DD}";
  return "\u{1F4C4}";
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    background: "#080808",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "0 16px",
    borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
    minHeight: 42,
  },
  tabs: { display: "flex", gap: 0 },
  tab: {
    background: "transparent",
    border: "none",
    borderBottom: "2px solid transparent",
    color: "#666",
    padding: "10px 16px",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    letterSpacing: 0.5,
  },
  tabActive: {
    color: "#d0d0d0",
    borderBottom: "2px solid #3b82f6",
  },
  headerActions: { display: "flex", gap: 8 },
  refreshBtn: {
    background: "transparent",
    color: "#888",
    border: "1px solid rgba(255, 255, 255, 0.1)",
    borderRadius: 4,
    padding: "4px 12px",
    fontSize: 12,
    cursor: "pointer",
  },
  downloadBtn: {
    background: "rgba(59, 130, 246, 0.2)",
    color: "#93c5fd",
    border: "1px solid rgba(59, 130, 246, 0.3)",
    borderRadius: 4,
    padding: "4px 12px",
    fontSize: 12,
    cursor: "pointer",
  },
  // Files tab layout
  filesLayout: {
    flex: 1,
    display: "flex",
    overflow: "hidden",
  },
  fileTree: {
    width: 260,
    minWidth: 200,
    borderRight: "1px solid rgba(255, 255, 255, 0.06)",
    overflowY: "auto",
    padding: "8px 0",
  },
  noFiles: {
    fontSize: 12,
    color: "#555",
    textAlign: "center",
    padding: "30px 16px",
  },
  fileItem: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    width: "100%",
    background: "transparent",
    border: "none",
    borderLeft: "2px solid transparent",
    color: "#999",
    padding: "5px 12px",
    fontSize: 12,
    fontFamily: "monospace",
    cursor: "pointer",
    textAlign: "left",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  fileItemActive: {
    background: "rgba(59, 130, 246, 0.08)",
    borderLeftColor: "#3b82f6",
    color: "#d0d0d0",
  },
  fileIcon: { fontSize: 11, flexShrink: 0 },
  fileName: { overflow: "hidden", textOverflow: "ellipsis" },
  fileViewer: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },
  fileViewerHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "8px 16px",
    borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
    background: "rgba(0, 0, 0, 0.3)",
  },
  fileViewerPath: {
    fontSize: 12,
    fontFamily: "monospace",
    color: "#93c5fd",
  },
  fileViewerSize: {
    fontSize: 11,
    color: "#555",
  },
  fileViewerContent: {
    flex: 1,
    margin: 0,
    padding: 16,
    overflowY: "auto",
    fontSize: 12,
    lineHeight: 1.6,
    fontFamily: "'SF Mono', Monaco, 'Cascadia Code', monospace",
    color: "#c8c8c8",
    background: "#0a0a0a",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },
  fileViewerEmpty: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 13,
    color: "#444",
  },
  // Preview tab
  previewArea: {
    flex: 1,
    position: "relative",
    overflow: "hidden",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#000",
  },
  iframe: { width: "100%", height: "100%", border: "none", background: "#000" },
  placeholder: {
    width: "100%",
    height: "100%",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    position: "relative",
  },
  animatedBg: {
    position: "absolute",
    inset: 0,
    background:
      "linear-gradient(135deg, #0a0a2e 0%, #1a0a3e 25%, #0a1a2e 50%, #0a0a2e 75%, #1a0a3e 100%)",
    backgroundSize: "400% 400%",
    animation: "gradientShift 8s ease infinite",
    opacity: 0.3,
  },
  placeholderContent: { position: "relative", textAlign: "center", padding: 40 },
  placeholderTitle: { fontSize: 18, fontWeight: 600, color: "#555", marginBottom: 8 },
  placeholderText: { fontSize: 13, color: "#444", lineHeight: 1.5, maxWidth: 300 },
  loadingSpinner: {
    width: 32,
    height: 32,
    border: "3px solid rgba(255, 255, 255, 0.1)",
    borderTop: "3px solid #3b82f6",
    borderRadius: "50%",
    animation: "spin 1s linear infinite",
    marginBottom: 16,
  },
  renderInfo: {
    padding: "8px 16px",
    borderTop: "1px solid rgba(255, 255, 255, 0.06)",
    background: "rgba(0, 0, 0, 0.4)",
  },
  exportBtn: {
    background: "rgba(34, 197, 94, 0.2)",
    color: "#86efac",
    border: "1px solid rgba(34, 197, 94, 0.3)",
    borderRadius: 4,
    padding: "4px 12px",
    fontSize: 12,
    cursor: "pointer",
    fontWeight: 600,
  },
  exportBtnDisabled: {
    opacity: 0.6,
    cursor: "not-allowed",
  },
  exportOverlay: {
    position: "absolute" as const,
    bottom: 0,
    left: 0,
    right: 0,
    padding: "12px 16px",
    background: "rgba(0, 0, 0, 0.8)",
    backdropFilter: "blur(8px)",
    zIndex: 10,
  },
  exportProgressTrack: {
    width: "100%",
    height: 4,
    background: "rgba(255, 255, 255, 0.1)",
    borderRadius: 2,
    overflow: "hidden",
  },
  exportProgressBar: {
    height: "100%",
    background: "linear-gradient(90deg, #22c55e, #3b82f6)",
    borderRadius: 2,
    transition: "width 0.3s ease",
  },
  exportText: {
    fontSize: 12,
    color: "#86efac",
    marginTop: 6,
    textAlign: "center" as const,
  },
  renderText: { fontSize: 12, color: "#666" },
  code: {
    background: "rgba(255, 255, 255, 0.06)",
    padding: "2px 6px",
    borderRadius: 3,
    fontSize: 11,
    color: "#93c5fd",
    fontFamily: "monospace",
  },
};
