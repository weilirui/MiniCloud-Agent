/**
 * Skills API client.
 */

export interface SkillInfo {
  name: string;
  description: string;
  trigger: string | null;
  parameters: Record<string, unknown>;
  source: string;
}

export async function listSkills(): Promise<{ items: SkillInfo[]; count: number }> {
  const resp = await fetch('/api/v1/skills/');
  if (!resp.ok) throw new Error(`list skills failed: ${resp.status}`);
  return resp.json();
}

export async function invokeSkill(name: string, args: Record<string, unknown>): Promise<{ name: string; result: string }> {
  const resp = await fetch('/api/v1/skills/invoke', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, arguments: args }),
  });
  if (!resp.ok) throw new Error(`invoke skill failed: ${resp.status}`);
  return resp.json();
}