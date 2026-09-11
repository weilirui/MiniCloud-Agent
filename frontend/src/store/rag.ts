/**
 * RAG store.
 */

import { create } from 'zustand';
import { DocOut, listDocs, uploadDoc, deleteDoc } from '../api/rag';

interface RagState {
  docs: DocOut[];
  uploading: boolean;
  load: () => Promise<void>;
  upload: (file: File) => Promise<void>;
  remove: (id: string) => Promise<void>;
}

export const useRagStore = create<RagState>((set) => ({
  docs: [],
  uploading: false,

  load: async () => {
    try {
      const data = await listDocs();
      set({ docs: data.items });
    } catch {
      // ignore
    }
  },

  upload: async (file) => {
    set({ uploading: true });
    try {
      const { doc } = await uploadDoc(file);
      set((state) => ({ docs: [doc, ...state.docs] }));
    } finally {
      set({ uploading: false });
    }
  },

  remove: async (id) => {
    await deleteDoc(id);
    set((state) => ({ docs: state.docs.filter((d) => d.id !== id) }));
  },
}));