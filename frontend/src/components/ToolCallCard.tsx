/**
 * ToolCallCard — visualization of a single tool/Skill/MCP invocation.
 */
import { useState } from 'react';
import clsx from 'clsx';
import type { ToolCallDisplay } from '../store/session';

const SOURCE_COLOR: Record<string, string> = {
  skill: 'bg-accent',
  mcp: 'bg-emerald-600',
  builtin: 'bg-slate-600',
};

export default function ToolCallCard({ tc }: { tc: ToolCallDisplay }) {
  const [expanded, setExpanded] = useState(false);
  const source = tc.name.startsWith('skill_')
    ? 'skill'
    : tc.name.startsWith('mcp__')
    ? 'mcp'
    : 'builtin';

  const displayName = tc.name.startsWith('mcp__')
    ? tc.name.split('__').slice(1).join('__')
    : tc.name.replace(/^skill_/, '');

  const statusColor =
    tc.status === 'error'
      ? 'text-danger'
      : tc.status === 'running'
      ? 'text-amber-400 animate-pulse'
      : 'text-success';

  return (
    <div className="bg-bg-card border border-white/5 rounded-lg overflow-hidden my-2 text-sm">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-3 py-2 flex items-center gap-2 hover:bg-white/5 transition"
      >
        <span className={clsx('w-2 h-2 rounded-full', SOURCE_COLOR[source])} />
        <span className="font-mono text-text-primary">{displayName}</span>
        <span className={clsx('text-xs ml-auto', statusColor)}>
          {tc.status === 'running' ? '⏳ running' :
           tc.status === 'error' ? '✗ error' :
           tc.duration_ms ? `✓ ${tc.duration_ms}ms` : '✓'}
        </span>
        <span className="text-text-muted text-xs">{expanded ? '▾' : '▸'}</span>
      </button>

      {expanded && (
        <div className="border-t border-white/5 px-3 py-2 space-y-2">
          <div>
            <div className="text-xs text-text-muted mb-1">Arguments</div>
            <pre className="text-xs bg-black/30 p-2 rounded overflow-x-auto">
              {JSON.stringify(tc.arguments, null, 2)}
            </pre>
          </div>
          {tc.result && (
            <div>
              <div className="text-xs text-text-muted mb-1">Result</div>
              <pre className="text-xs bg-black/30 p-2 rounded overflow-x-auto max-h-60 overflow-y-auto">
                {tc.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}