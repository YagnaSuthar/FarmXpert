// ============================================================
// FILE: src/components/dashboard/Markdown.jsx
//
// A small, safe Markdown renderer for assistant answers: headings,
// paragraphs, bullet and numbered lists, tables, **bold**, *italic*
// and `code`. It builds React elements (never raw HTML), and it is
// tolerant of half-written text, because answers render while they
// stream in: an unclosed ** simply shows as text until it closes.
// ============================================================

import { Fragment } from 'react';

const INLINE = /(\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\s][^*\n]*\*|_[^_\s][^_\n]*_|`[^`\n]+`)/g;

function inline(text, key = 'i') {
  const parts = text.split(INLINE);
  return parts.map((part, i) => {
    const k = `${key}${i}`;
    if (!part) return null;
    if ((part.startsWith('**') && part.endsWith('**')) || (part.startsWith('__') && part.endsWith('__'))) {
      return <strong key={k} className="font-semibold text-ink">{inline(part.slice(2, -2), k)}</strong>;
    }
    if (part.length > 2 && part.startsWith('`') && part.endsWith('`')) {
      return <code key={k} className="rounded-md bg-sage px-1.5 py-0.5 text-[0.88em] text-leaf">{part.slice(1, -1)}</code>;
    }
    if (part.length > 2 && ((part.startsWith('*') && part.endsWith('*')) || (part.startsWith('_') && part.endsWith('_')))) {
      return <em key={k} className="italic">{part.slice(1, -1)}</em>;
    }
    return <Fragment key={k}>{part}</Fragment>;
  });
}

const BULLET = /^\s*[-*•]\s+/;
const NUMBER = /^\s*\d+[.)]\s+/;
const HEADING = /^(#{1,4})\s+(.*)$/;
const ROW = /^\s*\|.*\|\s*$/;
const DIVIDER = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

const cells = (line) => line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());

/** Split the text into blocks: {type, ...}. */
function blocks(text) {
  const lines = text.replace(/\r/g, '').split('\n');
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i += 1; continue; }
    const h = line.match(HEADING);
    if (h) { out.push({ type: 'h', level: h[1].length, text: h[2] }); i += 1; continue; }
    if (ROW.test(line)) {
      const rows = [];
      while (i < lines.length && ROW.test(lines[i])) { rows.push(lines[i]); i += 1; }
      const hasHead = rows.length > 1 && DIVIDER.test(rows[1]);
      const body = rows.filter((r, n) => !(hasHead && n === 1)).map(cells);
      out.push({ type: 'table', head: hasHead ? body[0] : null, rows: hasHead ? body.slice(1) : body });
      continue;
    }
    if (BULLET.test(line) || NUMBER.test(line)) {
      const ordered = NUMBER.test(line);
      const re = ordered ? NUMBER : BULLET;
      const items = [];
      while (i < lines.length && re.test(lines[i])) {
        let item = lines[i].replace(re, '');
        i += 1;
        // continuation lines (indented, not a new item)
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !BULLET.test(lines[i]) && !NUMBER.test(lines[i])) {
          item += ` ${lines[i].trim()}`; i += 1;
        }
        items.push(item);
      }
      out.push({ type: ordered ? 'ol' : 'ul', items });
      continue;
    }
    const para = [line];
    i += 1;
    while (i < lines.length && lines[i].trim() && !HEADING.test(lines[i]) && !ROW.test(lines[i])
      && !BULLET.test(lines[i]) && !NUMBER.test(lines[i])) { para.push(lines[i]); i += 1; }
    out.push({ type: 'p', text: para.join('\n') });
  }
  return out;
}

export default function Markdown({ text, caret = false }) {
  const list = blocks(text || '');
  return (
    <div className="fx-md space-y-3 text-[0.97rem] leading-[1.7] text-ink/90">
      {list.map((b, n) => {
        const key = `b${n}`;
        const last = caret && n === list.length - 1;
        const tail = last ? <span className="fx-caret" aria-hidden /> : null;
        if (b.type === 'h') {
          return (
            <h3 key={key} className="!font-sans pt-1 text-[1.02rem] font-semibold tracking-normal text-ink">
              {inline(b.text, key)}{tail}
            </h3>
          );
        }
        if (b.type === 'ul' || b.type === 'ol') {
          const Tag = b.type;
          return (
            <Tag key={key} className="space-y-1.5">
              {b.items.map((item, j) => (
                <li key={`${key}-${j}`} className="relative pl-6">
                  {b.type === 'ul'
                    ? <span className="absolute top-[0.72em] left-1.5 size-1.5 rounded-full bg-gold" aria-hidden />
                    : <span className="absolute top-0 left-0 text-sm font-semibold text-leaf tabular-nums">{j + 1}.</span>}
                  {inline(item, `${key}-${j}`)}{last && j === b.items.length - 1 ? tail : null}
                </li>
              ))}
            </Tag>
          );
        }
        if (b.type === 'table') {
          return (
            <div key={key} className="no-scrollbar -mx-1 overflow-x-auto">
              <table className="w-full min-w-[18rem] border-separate border-spacing-0 overflow-hidden rounded-xl border border-line text-sm">
                {b.head && (
                  <thead>
                    <tr className="bg-sage/70">
                      {b.head.map((c, j) => (
                        <th key={j} className="border-b border-line px-3 py-2 text-left text-xs font-semibold tracking-wide text-ink">{inline(c, `${key}h${j}`)}</th>
                      ))}
                    </tr>
                  </thead>
                )}
                <tbody>
                  {b.rows.map((row, r) => (
                    <tr key={r} className="even:bg-canvas">
                      {row.map((c, j) => (
                        <td key={j} className="border-b border-line/70 px-3 py-2 align-top text-ink/85 tabular-nums">{inline(c, `${key}${r}-${j}`)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {tail}
            </div>
          );
        }
        return <p key={key} className="whitespace-pre-wrap">{inline(b.text, key)}{tail}</p>;
      })}
      {list.length === 0 && caret && <span className="fx-caret" aria-hidden />}
    </div>
  );
}
