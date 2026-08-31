import React from "react";

function inlineMarkdown(value) {
  const parts = value.split(/(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`)/g);
  return parts.map((part, index) => {
    if ((part.startsWith("**") && part.endsWith("**")) || (part.startsWith("__") && part.endsWith("__"))) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={index} className="rounded bg-slate-950 px-1 py-0.5 text-sky-300">{part.slice(1, -1)}</code>;
    }
    return <React.Fragment key={index}>{part}</React.Fragment>;
  });
}

export default function MarkdownText({ children }) {
  const lines = String(children ?? "").split("\n");
  const blocks = [];
  let list = null;
  let code = null;

  function flushList() {
    if (!list) return;
    const ListTag = list.ordered ? "ol" : "ul";
    blocks.push(
      <ListTag key={`list-${blocks.length}`} className="my-1 list-inside space-y-1 pl-2">
        {list.items.map((item, index) => <li key={index}>{inlineMarkdown(item)}</li>)}
      </ListTag>,
    );
    list = null;
  }

  function flushCode() {
    if (code === null) return;
    blocks.push(
      <pre key={`code-${blocks.length}`} className="my-2 overflow-x-auto rounded bg-slate-950 p-2 text-xs text-sky-200">
        <code>{code.join("\n")}</code>
      </pre>,
    );
    code = null;
  }

  lines.forEach((line, index) => {
    if (line.trim().startsWith("```")) {
      flushList();
      if (code === null) code = [];
      else flushCode();
      return;
    }
    if (code !== null) {
      code.push(line);
      return;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      const isOrdered = Boolean(ordered);
      if (!list || list.ordered !== isOrdered) {
        flushList();
        list = { ordered: isOrdered, items: [] };
      }
      list.items.push((unordered || ordered)[1]);
      return;
    }

    flushList();
    if (heading) {
      const Tag = heading[1].length === 1 ? "h3" : "h4";
      blocks.push(<Tag key={index} className="mt-2 font-semibold text-slate-100">{inlineMarkdown(heading[2])}</Tag>);
    } else if (line.trim()) {
      blocks.push(<p key={index} className="leading-5">{inlineMarkdown(line)}</p>);
    }
  });

  flushList();
  flushCode();
  return <div className="space-y-1">{blocks}</div>;
}
