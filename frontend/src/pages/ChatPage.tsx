/**
 * ChatPage — main page: SessionList + Chat + SkillPanel + input.
 */
import { useEffect, useRef, useState } from 'react';
import { useSessionStore } from '../store/session';
import { useSkillsStore } from '../store/skills';
import { streamChat } from '../api/chat';
import ChatWindow from '../components/ChatWindow';
import SessionList from '../components/SessionList';
import SkillPanel from '../components/SkillPanel';
import SlashCommandHint from '../components/SlashCommandHint';

export default function ChatPage() {
  const [input, setInput] = useState('');
  const [showHint, setShowHint] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const loadSkills = useSkillsStore((s) => s.load);

  const {
    currentSessionId,
    messages,
    isStreaming,
    abortController,
    addUserMessage,
    startAssistantMessage,
    appendAssistantContent,
    finalizeAssistantMessage,
    addToolCall,
    updateToolCallResult,
    setStreaming,
    newSession,
  } = useSessionStore();

  useEffect(() => {
    loadSkills();
  }, [loadSkills]);

  const send = async () => {
    if (!input.trim() || isStreaming) return;
    const text = input.trim();
    setInput('');
    setShowHint(false);

    let sessionId = currentSessionId;
    if (!sessionId) {
      sessionId = await newSession();
    }

    addUserMessage(text);
    const assistantId = startAssistantMessage();

    const controller = new AbortController();
    setStreaming(true);

    try {
      await streamChat(
        { session_id: sessionId, message: text },
        {
          onStart: () => {},
          onContent: (delta) => {
            appendAssistantContent(assistantId, delta);
          },
          onToolStart: (tc) => {
            addToolCall(assistantId, {
              id: tc.id,
              name: tc.name,
              arguments: tc.arguments,
            });
          },
          onToolResult: (tr) => {
            updateToolCallResult(
              assistantId,
              tr.tool_call_id,
              tr.content,
              tr.status,
              tr.duration_ms
            );
          },
          onDone: (content) => {
            finalizeAssistantMessage(assistantId, content);
          },
          onError: (msg) => {
            appendAssistantContent(assistantId, `\n\n[Error] ${msg}`);
            finalizeAssistantMessage(assistantId, '');
          },
        },
        controller.signal
      );
    } catch (e: any) {
      appendAssistantContent(assistantId, `\n\n[Error] ${e.message || e}`);
      finalizeAssistantMessage(assistantId, '');
    } finally {
      setStreaming(false);
    }
  };

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const v = e.target.value;
    setInput(v);
    setShowHint(v.startsWith('/') && !v.includes(' '));
  };

  const abortRun = () => {
    abortController?.abort();
    setStreaming(false);
  };

  return (
    <div className="h-screen flex bg-bg text-text-primary">
      <SessionList />
      <div className="flex-1 flex flex-col">
        <ChatWindow />
        <div className="border-t border-white/5 p-3 bg-bg-panel relative">
          <SlashCommandHint visible={showHint} />
          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKey}
              placeholder="输入消息，回车发送，Shift+回车换行。输入 / 查看可用 Skills。"
              rows={1}
              className="flex-1 bg-bg-card text-text-primary rounded-lg px-3 py-2 resize-none max-h-40 outline-none focus:ring-1 focus:ring-accent text-sm"
              disabled={isStreaming}
              style={{ minHeight: '40px' }}
            />
            {isStreaming ? (
              <button
                onClick={abortRun}
                className="bg-danger hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm transition"
              >
                停止
              </button>
            ) : (
              <button
                onClick={send}
                disabled={!input.trim()}
                className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm transition"
              >
                发送
              </button>
            )}
          </div>
          <div className="text-xs text-text-muted mt-1.5 px-1">
            {messages.length} messages · session {currentSessionId?.slice(0, 8) || 'new'}
          </div>
        </div>
      </div>
      <SkillPanel />
    </div>
  );
}