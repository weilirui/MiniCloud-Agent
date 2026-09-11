/**
 * Slash command hint popup.
 */
import { useSkillsStore } from '../store/skills';

export default function SlashCommandHint({ visible }: { visible: boolean }) {
  const skills = useSkillsStore((s) => s.skills);
  if (!visible) return null;

  return (
    <div className="absolute bottom-full left-0 right-0 mb-1 bg-bg-panel border border-white/10 rounded-lg shadow-lg max-h-60 overflow-y-auto">
      {skills.map((s) => (
        <div
          key={s.name}
          className="px-3 py-2 hover:bg-white/5 cursor-default flex items-center justify-between"
        >
          <div>
            <code className="text-accent text-sm">{s.trigger || `/${s.name}`}</code>
            <div className="text-text-muted text-xs mt-0.5">{s.description}</div>
          </div>
        </div>
      ))}
    </div>
  );
}