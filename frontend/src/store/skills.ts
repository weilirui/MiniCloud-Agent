/**
 * Skills store.
 */

import { create } from 'zustand';
import { SkillInfo, listSkills } from '../api/skills';

interface SkillsState {
  skills: SkillInfo[];
  loading: boolean;
  load: () => Promise<void>;
}

export const useSkillsStore = create<SkillsState>((set) => ({
  skills: [],
  loading: false,
  load: async () => {
    set({ loading: true });
    try {
      const data = await listSkills();
      set({ skills: data.items, loading: false });
    } catch {
      set({ loading: false });
    }
  },
}));