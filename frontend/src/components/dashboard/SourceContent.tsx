import { RelevanceBadge } from "../../config/ConfigAnalysis";
import { createElement } from "react";
import type { RichBlock } from "../../types";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** The same safe Markdown renderer is used by the screen and exported reports. */
export default function SourceContent({ markdown, text = "" }: { markdown?: string; text?: string }) {
  return <><RelevanceBadge text={text || markdown || ""} />{markdown ? (
    <div className="source-content"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{
      img: ({alt}) => <span className="source-image-placeholder">[Image: {alt || "source illustration"}]</span>,
      code: ({children, className}) => <code className={className}>{typeof children === "string" ? children.replace(/\n$/, "") : children}</code>,
    }}>{markdown}</ReactMarkdown></div>
  ) : <span className="source-text">{text}</span>}</>;
}

export const sourceContentCss = `
.relevance-note { margin: .5em 0; padding: .5em .8em; border-left: 3px solid #b45309; background: #fffbeb; color: #78350f; font-size: .85em; }
.relevance-note ul { padding-left: 1.4em; margin: .35em 0; }
.source-image-placeholder { font-style: italic; }

.source-text { white-space: pre-wrap; overflow-wrap: anywhere; }
.source-content { line-height: 1.65; overflow-wrap: anywhere; }
.source-content p { margin: 0 0 .65em; }
.source-content th p:last-child, .source-content td p:last-child { margin-bottom: 0; }
.source-content h1, .source-content h2, .source-content h3,
.source-content h4, .source-content h5, .source-content h6 { font-weight: 600; margin: 1.2em 0 .5em; }
.source-content h1 { font-size: 1.4em; } .source-content h2 { font-size: 1.25em; }
.source-content h3 { font-size: 1.15em; }
.source-content h4, .source-content h5, .source-content h6 { font-size: 1em; }
.source-content h6 { margin: 0 0 .65em; }
.source-content ul, .source-content ol { padding-left: 1.6em; margin: .5em 0; }
.source-content ul { list-style: disc; } .source-content ol { list-style: decimal; }
.source-content li { margin: .2em 0; }
.source-content li p { margin-bottom: 0; }
.source-content pre { white-space: pre-wrap; padding: .8em; border: 1px solid #94a3b8; border-radius: 4px; margin: .6em 0; }
.source-content code { font-family: monospace; font-size: .95em; }
.source-content table { width: 100%; border-collapse: collapse; margin: .6em 0; }
.source-content th, .source-content td { border: 1px solid #94a3b8; padding: .5em; text-align: left !important; vertical-align: top; }
.source-content a { color: #0b6cb4; text-decoration: underline; }
.source-content blockquote { border-left: 3px solid #94a3b8; padding-left: 1em; margin: .6em 0; }
.source-content img { max-width: 100%; }
`;

export function SourceBlocks({ blocks }: { blocks: RichBlock[] }) {
  return <div className="source-content">{blocks.map((b, i) => {
    if (b.markdown) return <SourceContent key={i} markdown={b.markdown} />;
    switch (b.type) {
      case "heading": return createElement(`h${Math.min(6, Math.max(1, b.level ?? 2))}`, {key: i}, b.text);
      case "paragraph": return <p key={i}>{b.bold ? <strong>{b.text}</strong> : b.text}</p>;
      case "code": return <pre key={i}><code>{b.text}</code></pre>;
      case "list": return b.ordered
        ? <ol key={i} start={b.start ?? 1}>{b.items?.map((item, j) => <li key={j}>{b.itemBlocks?.[j] ? <SourceBlocks blocks={b.itemBlocks[j]} /> : item}</li>)}</ol>
        : <ul key={i}>{b.items?.map((item, j) => <li key={j}>{b.itemBlocks?.[j] ? <SourceBlocks blocks={b.itemBlocks[j]} /> : item}</li>)}</ul>;
      case "table": return <table key={i}>
        {!!b.headers?.length && <thead><tr>{b.headers.map((h, j) => (b.headerColSpans?.[j] === 0 ? null : <th key={j} colSpan={b.headerColSpans?.[j]}>{b.headerMarkdown?.[j] ? <SourceContent markdown={b.headerMarkdown[j]} /> : h}</th>))}</tr></thead>}
        <tbody>{b.rows?.map((r, j) => <tr key={j}>{r.map((c, k) => (b.rowSpans?.[j]?.[k] === 0 || b.colSpans?.[j]?.[k] === 0 ? null : <td key={k} rowSpan={b.rowSpans?.[j]?.[k]} colSpan={b.colSpans?.[j]?.[k]}>{b.cellBlocks?.[j]?.[k] ? <SourceBlocks blocks={b.cellBlocks[j][k]} /> : b.cellMarkdown?.[j]?.[k] ? <SourceContent markdown={b.cellMarkdown[j][k]} /> : c}</td>))}</tr>)}</tbody>
      </table>;
      default: return null;
    }
  })}</div>;
}
