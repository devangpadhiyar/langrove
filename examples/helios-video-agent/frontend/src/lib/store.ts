const API_URL = "";

export interface VfsFile {
  key: string;
  namespace: string[];
  value: { content: string; encoding?: string; created_at?: string; modified_at?: string };
  created_at?: string;
  updated_at?: string;
}

export interface CompositionMetadata {
  title: string;
  width: number;
  height: number;
  fps: number;
  duration: number;
}

/**
 * Get the URL for a VFS file served with proper MIME type.
 * The backend's /vfs/ endpoint serves raw files so relative imports work.
 */
export function getVfsUrl(threadId: string, filePath: string): string {
  const cleanPath = filePath.startsWith("/") ? filePath.slice(1) : filePath;
  return `${API_URL}/vfs/${threadId}/${cleanPath}`;
}

/**
 * Fetch the assembled composition HTML from the Store.
 */
export async function fetchComposition(
  threadId: string,
): Promise<string | null> {
  try {
    const res = await fetch(
      `${API_URL}/store/items?` +
        new URLSearchParams({
          namespace: `vfs/${threadId}`,
          key: "/dist/index.html",
        }),
    );
    if (!res.ok) return null;
    const item = await res.json();
    return item?.value?.content ?? null;
  } catch {
    return null;
  }
}

/**
 * Fetch composition metadata (dimensions, timing) written by assemble_composition.
 */
export async function fetchCompositionMetadata(
  threadId: string,
): Promise<CompositionMetadata | null> {
  try {
    const res = await fetch(
      `${API_URL}/store/items?` +
        new URLSearchParams({
          namespace: `vfs/${threadId}`,
          key: "/dist/metadata.json",
        }),
    );
    if (!res.ok) return null;
    const item = await res.json();
    const content = item?.value?.content;
    if (!content) return null;
    return JSON.parse(content);
  } catch {
    return null;
  }
}

/**
 * List all files in the VFS for a given thread.
 */
export async function listVfsFiles(threadId: string): Promise<VfsFile[]> {
  try {
    const res = await fetch(`${API_URL}/store/items/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        namespace_prefix: ["vfs", threadId],
        limit: 100,
      }),
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.items ?? [];
  } catch {
    return [];
  }
}

/**
 * Fetch a single file's content from the Store.
 */
export async function fetchFile(
  threadId: string,
  filePath: string,
): Promise<string | null> {
  try {
    const res = await fetch(
      `${API_URL}/store/items?` +
        new URLSearchParams({
          namespace: `vfs/${threadId}`,
          key: filePath,
        }),
    );
    if (!res.ok) return null;
    const item = await res.json();
    return item?.value?.content ?? null;
  } catch {
    return null;
  }
}
