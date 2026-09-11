/**
 * Session store (Zustand).
 */

import { create } from 'zustand';
import { MessageOut, SessionOut } from '../api/sessions';

export interface ToolCallDisplay {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  result?: string;
  status?: 'running' | 'ok' | 'error';
  duration_ms?: number;
}

export interface MessageDisplay {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  tool_calls?: ToolCallDisplay[];
  created_at: string;
  streaming?: boolean;
}

interface SessionState {
  sessions: SessionOut[];
  currentSessionId: string | null;
  messages: MessageDisplay[];
  isStreaming: boolean;
  abortController: AbortController | null;

  loadSessions: () => Promise<void>;
  selectSession: (id: string) => Promise<void>;
  newSession: (title?: string) => Promise<string>;
  deleteSession: (id: string) => Promise<void>;
  addUserMessage: (content: string) => void;
  startAssistantMessage: () => string;
  appendAssistantContent: (msgId: string, delta: string) => void;
  finalizeAssistantMessage: (msgId: string, fullContent: string) => void;
  addToolCall: (msgId: string, tc: ToolCallDisplay) => void;
  updateToolCallResult: (msgId: string, tcId: string, result: string, status: string, duration_ms?: number) => void;
  setStreaming: (s: boolean) => void;
  reset: () => void;
}

let msgCounter = 0;
const makeId = () => `msg_${Date.now()}_${++msgCounter}`;

export const useSessionStore = create<SessionState>((set) => ({
  sessions: [],
  currentSessionId: null,
  messages: [],
  isStreaming: false,
  abortController: null,

  loadSessions: async () => {
    const { listSessions } = await import('../api/sessions');
    const data = await listSessions();
    set({ sessions: data.items });
  },

  selectSession: async (id) => {
    const { getSession } = await import('../api/sessions');
    const detail = await getSession(id);
    set({
      currentSessionId: id,
      messages: detail.messages.map((m: MessageOut) => ({
        id: m.id,
        role: m.role as any,
        content: m.content || '',
        tool_calls: m.tool_calls?.map((tc) => ({
          id: tc.id,
          name: tc.name,
          arguments: tc.arguments,
          status: 'ok' as const,
        })),
        created_at: m.created_at,
      })),
    });
  },

  newSession: async (title) => {
    const { createSession } = await import('../api/sessions');
    const s = await createSession(title);
    set((state) => ({
      sessions: [s, ...state.sessions],
      currentSessionId: s.id,
      messages: [],
    }));
    return s.id;
  },

  deleteSession: async (id) => {
    const { deleteSession } = await import('../api/sessions');
    await deleteSession(id);
    set((state) => ({
      sessions: state.sessions.filter((s) => s.id !== id),
      currentSessionId: state.currentSessionId === id ? null : state.currentSessionId,
      messages: state.currentSessionId === id ? [] : state.messages,
    }));
  },

  addUserMessage: (content) => {
    const msg: MessageDisplay = {
      id: makeId(),
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };
    set((state) => ({ messages: [...state.messages, msg] }));
  },

  startAssistantMessage: () => {
    const id = makeId();
    const msg: MessageDisplay = {
      id,
      role: 'assistant',
      content: '',
      tool_calls: [],
      created_at: new Date().toISOString(),
      streaming: true,
    };
    set((state) => ({ messages: [...state.messages, msg] }));
    return id;
  },

  appendAssistantContent: (msgId, delta) => {
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === msgId ? { ...m, content: m.content + delta } : m
      ),
    }));
  },

  finalizeAssistantMessage: (msgId, fullContent) => {
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === msgId ? { ...m, content: fullContent || m.content, streaming: false } : m
      ),
    }));
  },

  addToolCall: (msgId, tc) => {
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === msgId
          ? { ...m, tool_calls: [...(m.tool_calls || []), { ...tc, status: 'running' }] }
          : m
      ),
    }));
  },

  updateToolCallResult: (msgId, tcId, result, status, duration_ms) => {
    set((state) => ({
      messages: state.messages.map((m) => {
        if (m.id !== msgId || !m.tool_calls) return m;
        return {
          ...m,
          tool_calls: m.tool_calls.map((tc) =>
            tc.id === tcId
              ? { ...tc, result, status: status as any, duration_ms }
              : tc
          ),
        };
      }),
    }));
  },

  setStreaming: (s) => set({ isStreaming: s }),

  reset: () =>
    set({ currentSessionId: null, messages: [], isStreaming: false, abortController: null }),
}));