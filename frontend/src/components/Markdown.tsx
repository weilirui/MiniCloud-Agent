/**
 * Markdown renderer with syntax highlighting.
 */
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import hljs from 'highlight.js/lib/common';

export default function Markdown({ content }: { content: string }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ inline, className, children, ...props }: any) {
            const match = /language-(\w+)/.exec(className || '');
            if (!inline && match) {
              const code = String(children).replace(/\n$/, '');
              let highlighted = code;
              try {
                if (hljs.getLanguage(match[1])) {
                  highlighted = hljs.highlight(code, { language: match[1] }).value;
                }
              } catch {
                /* fallback */
              }
              return (
                <pre>
                  <code
                    className={`hljs language-${match[1]}`}
                    dangerouslySetInnerHTML={{ __html: highlighted }}
                    {...props}
                  />
                </pre>
              );
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}