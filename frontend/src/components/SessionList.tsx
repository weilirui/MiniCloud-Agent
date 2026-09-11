/**
 * SessionList — left sidebar.
 */
import { useEffect } from 'react';
import { useSessionStore } from '../store/session';

export default function SessionList() {
  const {
    sessions,
    currentSessionId,
    loadSessions,
    selectSession,
    newSession,
    deleteSession,
  } = useSessionStore();

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  return (
    <div className="w-64 bg-bg-panel border-r border-white/5 flex flex-col">
      <div className="p-3 border-b border-white/5">
        <button
          onClick={() => newSession()}
          className="w-full bg-accent hover:bg-accent-hover text-white rounded px-3 py-2 text-sm font-medium transition"
        >
          + New Chat
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {sessions.length === 0 ? (
          <div className="p-4 text-text-muted text-sm">暂无会话</div>
        ) : (
          sessions.map((s) => (
            <div
              key={s.id}
              onClick={() => selectSession(s.id)}
              className={`group cursor-pointer px-3 py-2 border-b border-white/5 hover:bg-white/5 transition ${
                currentSessionId === s.id ? 'bg-white/10' : ''
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex-1 truncate text-sm">{s.title}</div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm(`Delete "${s.title}"?`)) deleteSession(s.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 text-text-muted hover:text-danger text-xs ml-2"
                >
                  ✗
                </button>
              </div>
              <div className="text-xs text-text-muted mt-0.5">
                {s.message_count} msgs · {new Date(s.updated_at).toLocaleDateString()}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}