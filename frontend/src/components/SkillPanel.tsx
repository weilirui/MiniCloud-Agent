/**
 * SkillPanel — right sidebar with available Skills + Knowledge base.
 */
import { useEffect, useState } from 'react';
import { useSkillsStore } from '../store/skills';
import { useRagStore } from '../store/rag';

type Tab = 'skills' | 'kb';

export default function SkillPanel() {
  const [tab, setTab] = useState<Tab>('skills');
  const { skills, load: loadSkills } = useSkillsStore();
  const { docs, uploading, load: loadDocs, upload, remove } = useRagStore();

  useEffect(() => {
    loadSkills();
    loadDocs();
  }, [loadSkills, loadDocs]);

  return (
    <div className="w-72 bg-bg-panel border-l border-white/5 flex flex-col">
      <div className="flex border-b border-white/5">
        <button
          onClick={() => setTab('skills')}
          className={`flex-1 px-3 py-2 text-sm ${
            tab === 'skills' ? 'bg-bg-card text-text-primary' : 'text-text-muted'
          }`}
        >
          Skills ({skills.length})
        </button>
        <button
          onClick={() => setTab('kb')}
          className={`flex-1 px-3 py-2 text-sm ${
            tab === 'kb' ? 'bg-bg-card text-text-primary' : 'text-text-muted'
          }`}
        >
          知识库 ({docs.length})
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 text-sm">
        {tab === 'skills' ? (
          skills.length === 0 ? (
            <div className="text-text-muted">加载中...</div>
          ) : (
            <div className="space-y-2">
              {skills.map((s) => (
                <div key={s.name} className="bg-bg-card rounded p-2.5">
                  <div className="flex items-center justify-between">
                    <code className="text-accent text-xs">{s.trigger || `/${s.name}`}</code>
                  </div>
                  <div className="text-text-primary mt-1 font-medium text-xs">{s.name}</div>
                  <div className="text-text-muted text-xs mt-1">{s.description}</div>
                </div>
              ))}
            </div>
          )
        ) : (
          <div className="space-y-2">
            <label className="block">
              <input
                type="file"
                accept=".md,.txt,.pdf,.py,.js,.ts,.go,.rs,.java,.c,.cpp,.rb,.json,.yaml,.yml,.xml,.html,.css"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  try {
                    await upload(file);
                  } catch (err) {
                    alert(`Upload failed: ${err}`);
                  }
                  e.target.value = '';
                }}
                disabled={uploading}
                className="block w-full text-xs text-text-muted file:mr-2 file:py-1.5 file:px-3 file:rounded file:border-0 file:bg-accent file:text-white file:cursor-pointer disabled:opacity-50"
              />
              {uploading && <div className="text-xs text-text-muted mt-1">上传中...</div>}
            </label>

            {docs.length === 0 ? (
              <div className="text-text-muted text-xs mt-4">暂无文档，上传一个开始。</div>
            ) : (
              docs.map((d) => (
                <div key={d.id} className="bg-bg-card rounded p-2.5 text-xs">
                  <div className="flex items-start justify-between">
                    <div className="flex-1 truncate">
                      <div className="font-medium text-text-primary truncate">{d.filename}</div>
                      <div className="text-text-muted mt-0.5">
                        {d.chunk_count} chunks · {(d.size_bytes || 0) / 1024 | 0} KB
                      </div>
                    </div>
                    <button
                      onClick={() => remove(d.id)}
                      className="text-text-muted hover:text-danger ml-2"
                    >
                      ✗
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}