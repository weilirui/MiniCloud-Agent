/**
 * MessageBubble — single chat message with optional tool calls.
 */
import Markdown from './Markdown';
import ToolCallCard from './ToolCallCard';
import type { MessageDisplay } from '../store/session';

export default function MessageBubble({ message }: { message: MessageDisplay }) {
  const isUser = message.role === 'user';
  const isAssistant = message.role === 'assistant';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-3xl rounded-lg px-4 py-3 ${
          isUser
            ? 'bg-accent text-white'
            : isAssistant
            ? 'bg-bg-card text-text-primary'
            : 'bg-bg-panel text-text-muted text-sm'
        }`}
      >
        {!isUser && message.role !== 'tool' && (
          <div className="text-xs text-text-muted mb-1 font-mono">
            {message.role}
            {message.streaming && <span className="ml-2 animate-pulse">●</span>}
          </div>
        )}

        {message.content && <Markdown content={message.content} />}

        {message.tool_calls && message.tool_calls.length > 0 && (
          <div className="mt-2 space-y-1">
            {message.tool_calls.map((tc) => (
              <ToolCallCard key={tc.id} tc={tc} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}