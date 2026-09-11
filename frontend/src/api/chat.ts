/**
 * Chat API client: SSE streaming.
 */

export interface ChatRequest {
  session_id?: string;
  message: string;
  model?: string;
  temperature?: number;
  stream?: boolean;
}

export interface ToolCallEvent {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface ToolResultEvent {
  tool_call_id: string;
  name: string;
  content: string;
  status: string;
  duration_ms?: number;
}

export type ChatEvent =
  | { type: 'start'; session_id: string }
  | { type: 'iteration'; n: number }
  | { type: 'content'; delta: string }
  | { type: 'tool_call_start'; id: string; name: string; arguments: Record<string, unknown> }
  | { type: 'tool_call_result'; tool_call_id: string; name: string; content: string; status: string; duration_ms?: number }
  | { type: 'done'; finish_reason: string; content: string }
  | { type: 'error'; message: string };

export interface ChatHandlers {
  onStart?: (session_id: string) => void;
  onContent?: (delta: string) => void;
  onToolStart?: (tc: ToolCallEvent) => void;
  onToolResult?: (tr: ToolResultEvent) => void;
  onDone?: (content: string, finish_reason: string) => void;
  onError?: (msg: string) => void;
}

export async function streamChat(
  req: ChatRequest,
  handlers: ChatHandlers,
  signal?: AbortSignal
): Promise<void> {
  const resp = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...req, stream: true }),
    signal,
  });

  if (!resp.ok || !resp.body) {
    const text = await resp.text();
    handlers.onError?.(text || `HTTP ${resp.status}`);
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Parse SSE: events separated by \n\n
    let idx;
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const eventBlock = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      parseEvent(eventBlock, handlers);
    }
  }
}

function parseEvent(block: string, handlers: ChatHandlers): void {
  let eventName = 'message';
  let dataLine = '';

  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLine += line.slice(5).trim();
    }
  }
  if (!dataLine) return;
  let data: any;
  try {
    data = JSON.parse(dataLine);
  } catch {
    data = dataLine;
  }

  switch (eventName) {
    case 'start':
      handlers.onStart?.(data.session_id);
      break;
    case 'content':
      handlers.onContent?.(data.delta || '');
      break;
    case 'tool_call_start':
      handlers.onToolStart?.({
        id: data.id,
        name: data.name,
        arguments: data.arguments || {},
      });
      break;
    case 'tool_call_result':
      handlers.onToolResult?.({
        tool_call_id: data.tool_call_id,
        name: data.name,
        content: data.content,
        status: data.status,
        duration_ms: data.duration_ms,
      });
      break;
    case 'done':
      handlers.onDone?.(data.content || '', data.finish_reason);
      break;
    case 'error':
      handlers.onError?.(data.message || 'unknown error');
      break;
  }
}

export async function chatCompletions(req: ChatRequest): Promise<{
  content: string;
  finish_reason: string;
  tool_calls: ToolCallEvent[];
  session_id: string;
}> {
  const resp = await fetch('/api/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...req, stream: false }),
  });
  if (!resp.ok) throw new Error(`chat failed: ${resp.status}`);
  return resp.json();
}