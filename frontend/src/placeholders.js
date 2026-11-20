// Typed placeholders in AI rewrites, e.g. "[X%]", "[N users]", "[€X]", "[X]-second".
// Each one becomes an input of the right type; the bullet can't be used until
// every placeholder has a valid value.

export const ANY_BRACKET = /\[[^\]]*\]/;
const BRACKETS = /\[([^\]]*)\]/g;
const CURRENCY = /[$€£₹]/;

/** Work out what kind of value a placeholder wants from its text. */
function classify(inner) {
  const text = inner.trim();
  const currency = text.match(CURRENCY)?.[0];
  if (currency) {
    return { kind: "money", symbol: currency, label: `Amount (${currency})` };
  }
  if (text.includes("%")) {
    return { kind: "percent", label: "Percentage" };
  }
  // "N", "X", "#", optionally followed by a unit: "N users", "X hours", "X+ teams"
  const m = text.match(/^(?:N|X|Y|Z|#)\+?\s*(.*)$/i);
  if (m) {
    const unit = m[1].trim();
    const integer = /^N\b/i.test(text) || /^#/.test(text);
    return { kind: integer ? "count" : "number", unit, label: unit ? `Number of ${unit}` : "Number" };
  }
  return { kind: "text", label: text || "Text" };
}

/** All placeholders in `text`, in order, with their position and type. */
export function parsePlaceholders(text) {
  const out = [];
  for (const m of text.matchAll(BRACKETS)) {
    out.push({ id: `${out.length}:${m[0]}`, raw: m[0], start: m.index, end: m.index + m[0].length,
               ...classify(m[1]) });
  }
  return out;
}

/** Returns an error message, or null if `value` is valid for this placeholder. */
export function validate(ph, value) {
  const v = (value ?? "").trim();
  if (!v) return "Required";
  if (ph.kind === "text") {
    if (v.length > 40) return "Keep it under 40 characters";
    if (/[[\]]/.test(v)) return "No brackets";
    return null;
  }
  if (!/^\d+(\.\d+)?$/.test(v)) return "Enter a number";
  const n = Number(v);
  if (ph.kind === "count" && !Number.isInteger(n)) return "Whole number only";
  if (n <= 0) return "Must be more than 0";
  if (ph.kind === "percent" && n > 1000) return "That percentage looks too high";
  if (n > 1e12) return "Too large";
  return null;
}

function render(ph, value) {
  const v = value.trim();
  const num = ph.kind === "text" ? v : Number(v).toLocaleString("en-US", { maximumFractionDigits: 2 });
  switch (ph.kind) {
    case "percent": return `${num}%`;
    case "money": return `${ph.symbol}${num}`;
    case "count":
    case "number": return ph.unit ? `${num} ${ph.unit}` : num;
    default: return v;
  }
}

/**
 * Fill placeholders with valid values. Invalid or empty ones are left as
 * "[...]" so the bullet still counts as unfilled and can't be downloaded.
 */
export function fill(text, values) {
  const phs = parsePlaceholders(text);
  let out = "";
  let pos = 0;
  for (const ph of phs) {
    const value = values[ph.id];
    out += text.slice(pos, ph.start) + (validate(ph, value) ? ph.raw : render(ph, value));
    pos = ph.end;
  }
  return out + text.slice(pos);
}

export function allFilled(text, values) {
  return parsePlaceholders(text).every((ph) => !validate(ph, values[ph.id]));
}

export function inputType(ph) {
  return ph.kind === "text" ? "text" : "number";
}
