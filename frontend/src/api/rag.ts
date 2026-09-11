/**
 * RAG API client.
 */

export interface DocOut {
  id: string;
  filename: string;
  source_type: string;
  mime_type: string | null;
  size_bytes: number | null;
  chunk_count: number;
  created_at: string;
}

export interface QueryHit {
  text: string;
  source: string;
  score: number;
  metadata: Record<string, unknown>;
}

export interface QueryResult {
  query: string;
  hits: QueryHit[];
  count: number;
}

export async function uploadDoc(file: File): Promise<{ doc: DocOut; message: string }> {
  const form = new FormData();
  form.append('file', file);
  const resp = await fetch('/api/v1/rag/upload', {
    method: 'POST',
    body: form,
  });
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`upload failed: ${resp.status} ${t}`);
  }
  return resp.json();
}

export async function queryRag(
  q: string,
  top_k = 5,
  score_threshold = 0.5
): Promise<QueryResult> {
  const resp = await fetch('/api/v1/rag/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: q, top_k, score_threshold }),
  });
  if (!resp.ok) throw new Error(`query failed: ${resp.status}`);
  return resp.json();
}

export async function listDocs(): Promise<{ items: DocOut[]; count: number }> {
  const resp = await fetch('/api/v1/rag/docs');
  if (!resp.ok) throw new Error(`list docs failed: ${resp.status}`);
  return resp.json();
}

export async function deleteDoc(id: string): Promise<{ deleted: number }> {
  const resp = await fetch(`/api/v1/rag/docs/${id}`, { method: 'DELETE' });
  if (!resp.ok) throw new Error(`delete failed: ${resp.status}`);
  return resp.json();
}