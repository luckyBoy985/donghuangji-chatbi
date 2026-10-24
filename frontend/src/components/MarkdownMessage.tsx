import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

import { linkCitations } from "../lib/citations";

interface Props {
  content: string;
  onCitationClick?: (key: string) => void;
}

export function MarkdownMessage({ content, onCitationClick }: Props) {
  return (
    <div className="markdown-content">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={{
          a({ href, children, ...props }) {
            if (href?.startsWith("#citation-")) {
              const key = href.replace("#citation-", "");
              return (
                <button
                  type="button"
                  className="inline-citation"
                  onClick={() => onCitationClick?.(key)}
                >
                  {children}
                </button>
              );
            }
            return (
              <a
                href={href}
                target="_blank"
                rel="noreferrer noopener"
                {...props}
              >
                {children}
              </a>
            );
          },
        }}
      >
        {linkCitations(content)}
      </ReactMarkdown>
    </div>
  );
}
