/**
 * ChatWindow — main chat panel.
 */
import { useEffect, useRef } from 'react';
import { useSessionStore } from '../store/session';
import MessageBubble from './MessageBubble';

export default function ChatWindow() {
  const messages = useSessionStore((s) => s.messages);
  const isStreaming = useSessionStore((s) => s.isStreaming);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages.length, messages[messages.length - 1]?.content]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4" ref={scrollRef}>
      {messages.length === 0 ? (
        <div className="h-full flex flex-col items-center justify-center text-text-muted">
          <div className="text-2xl mb-2">👋</div>
          <div className="text-lg">minicloud-agent</div>
          <div className="text-sm mt-2">
            输入 <code className="bg-bg-card px-1.5 py-0.5 rounded">/</code> 查看可用 Skills
          </div>
        </div>
      ) : (
        messages.map((m) => <MessageBubble key={m.id} message={m} />)
      )}
      {isStreaming && (
        <div className="text-xs text-text-muted animate-pulse ml-2">streaming...</div>
      )}
    </div>
  );
}