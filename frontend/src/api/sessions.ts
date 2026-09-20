/**
 * Sessions API client.
 */

export interface SessionOut {
  id: string;
  title: string;
  model: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface MessageOut {
  id: string;
  role: string;
  content: string | null;
  tool_calls?: Array<{ id: string; name: string; arguments: Record<string, unknown> }>;
  tool_call_id?: string;
  name?: string | null;
  created_at: string;
}

export interface SessionDetail extends SessionOut {
  system_prompt: string | null;
  messages: MessageOut[];
}

export async function listSessions(limit = 50): Promise<{ items: SessionOut[]; total: number }> {
  const resp = await fetch(`/api/v1/sessions/?limit=${limit}`);
  if (!resp.ok) throw new Error(`list sessions failed: ${resp.status}`);
  return resp.json();
}

export async function createSession(title?: string, model?: string): Promise<SessionOut> {
  const resp = await fetch('/api/v1/sessions/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, model }),
  });
  if (!resp.ok) throw new Error(`create session failed: ${resp.status}`);
  return resp.json();
}

export async function getSession(id: string): Promise<SessionDetail> {
  const resp = await fetch(`/api/v1/sessions/${id}`);
  if (!resp.ok) throw new Error(`get session failed: ${resp.status}`);
  return resp.json();
}

export async function deleteSession(id: string): Promise<{ deleted: number }> {
  const resp = await fetch(`/api/v1/sessions/${id}`, { method: 'DELETE' });
  if (!resp.ok) throw new Error(`delete session failed: ${resp.status}`);
  return resp.json();
}

export async function updateSession(
  id: string,
  patch: { title?: string; model?: string; system_prompt?: string }
): Promise<SessionOut> {
  const resp = await fetch(`/api/v1/sessions/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!resp.ok) throw new Error(`update session failed: ${resp.status}`);
  return resp.json();
}