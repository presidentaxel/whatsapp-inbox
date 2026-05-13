/**
 * Rendu Markdown ultra-léger pour les réponses Axelia.
 *
 * Supporté :
 *   - **gras** / __gras__
 *   - *italique* / _italique_
 *   - `code inline`
 *   - listes à tirets `- ` ou `* ` (groupées en <ul>)
 *   - listes ordonnées `1. ` (groupées en <ol>)
 *   - liens [label](url)
 *   - sauts de ligne et lignes vides (espacement vertical respecté)
 *
 * Volontairement pas de support :
 *   - titres `#` (le prompt système l’interdit côté Axelia)
 *   - blocs de code triple backticks (rare en réponse Axelia, ajouter si besoin)
 *   - tableaux
 *
 * Le but : rendre les listes propres et le gras sans importer une dépendance.
 */

const _safeUrl = (url) => {
  const s = String(url || "").trim();
  if (!s) return null;
  if (/^(https?:|mailto:|tel:)/i.test(s)) return s;
  if (/^\//.test(s)) return s;
  return null;
};

function renderInlineTokens(text, keyPrefix = "") {
  const out = [];
  const src = String(text ?? "");
  if (!src) return out;

  // Ordre : code inline > gras > italique > liens
  const re =
    /(`([^`\n]+)`|\*\*([^*\n]+)\*\*|__([^_\n]+)__|(?<![\w*])\*([^*\n]+?)\*(?!\w)|(?<![\w_])_([^_\n]+?)_(?!\w)|\[([^\]\n]+)\]\(([^)\s]+)\))/g;

  let last = 0;
  let m;
  let n = 0;
  while ((m = re.exec(src)) !== null) {
    if (m.index > last) {
      out.push(src.slice(last, m.index));
    }
    const k = `${keyPrefix}-tok-${n++}`;
    if (m[2] !== undefined) {
      out.push(
        <code key={k} className="axelia-md-code">
          {m[2]}
        </code>,
      );
    } else if (m[3] !== undefined || m[4] !== undefined) {
      out.push(
        <strong key={k} className="axelia-md-strong">
          {m[3] ?? m[4]}
        </strong>,
      );
    } else if (m[5] !== undefined || m[6] !== undefined) {
      out.push(
        <em key={k} className="axelia-md-em">
          {m[5] ?? m[6]}
        </em>,
      );
    } else if (m[7] && m[8]) {
      const safe = _safeUrl(m[8]);
      if (safe) {
        out.push(
          <a
            key={k}
            href={safe}
            target="_blank"
            rel="noopener noreferrer"
            className="axelia-md-link"
          >
            {m[7]}
          </a>,
        );
      } else {
        out.push(m[0]);
      }
    } else {
      out.push(m[0]);
    }
    last = m.index + m[0].length;
  }
  if (last < src.length) out.push(src.slice(last));
  return out;
}

/** Découpe un texte en blocs (liste / paragraphe). */
function blockify(text) {
  const lines = String(text ?? "").split(/\r?\n/);
  const blocks = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const ulMatch = line.match(/^\s*[-*]\s+(.+)$/);
    const olMatch = line.match(/^\s*(\d+)[.)]\s+(.+)$/);

    if (ulMatch) {
      const items = [];
      while (i < lines.length) {
        const m = lines[i].match(/^\s*[-*]\s+(.+)$/);
        if (!m) break;
        items.push(m[1]);
        i += 1;
      }
      blocks.push({ kind: "ul", items });
      continue;
    }

    if (olMatch) {
      const items = [];
      while (i < lines.length) {
        const m = lines[i].match(/^\s*(\d+)[.)]\s+(.+)$/);
        if (!m) break;
        items.push(m[2]);
        i += 1;
      }
      blocks.push({ kind: "ol", items });
      continue;
    }

    blocks.push({ kind: "line", text: line });
    i += 1;
  }
  return blocks;
}

export function renderMarkdown(text) {
  const blocks = blockify(text);
  const elements = [];
  blocks.forEach((b, idx) => {
    const key = `b-${idx}`;
    if (b.kind === "ul") {
      elements.push(
        <ul key={key} className="axelia-md-list">
          {b.items.map((it, j) => (
            <li key={`${key}-li-${j}`}>{renderInlineTokens(it, `${key}-${j}`)}</li>
          ))}
        </ul>,
      );
    } else if (b.kind === "ol") {
      elements.push(
        <ol key={key} className="axelia-md-list axelia-md-list--ol">
          {b.items.map((it, j) => (
            <li key={`${key}-li-${j}`}>{renderInlineTokens(it, `${key}-${j}`)}</li>
          ))}
        </ol>,
      );
    } else {
      const trimmed = b.text;
      elements.push(
        <span key={key} className="axelia-md-line">
          {renderInlineTokens(trimmed, key)}
          {idx < blocks.length - 1 ? <br /> : null}
        </span>,
      );
    }
  });
  return elements;
}
