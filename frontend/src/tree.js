// Pure logic on the results: folder tree and selection rules.
// Files inside archives are only reported: they are never selectable.

export const loose = g => g.files.filter(f => !f.chain);
// With "copies in archives count as kept" (arcOk), a group may lose every disk copy
// as long as it has a copy inside an archive (the server checks the archive is unchanged).
export const hasArc = g => g.files.some(f => f.chain);
export const allowAllDisk = (g, arcOk) => arcOk && hasArc(g);

function splitPath(p) {
  let prefix = '';
  if (p.startsWith('\\\\')) { prefix = '\\\\'; p = p.slice(2); }
  else if (p.startsWith('/')) { prefix = '/'; p = p.slice(1); }
  const parts = p.split(/[\\/]+/).filter(Boolean);
  if (prefix) parts[0] = prefix + parts[0];
  else if (/^[A-Za-z]:$/.test(parts[0])) parts[0] += '\\';
  return parts;
}

const joinName = (a, b, sep) => (a.endsWith(sep) ? a + b : a + sep + b);
const newNode = (name, full) => ({ name, full, dirs: new Map(), files: [], size: 0, count: 0, archive: false, inArc: false });

/* Splits a path into parts; for files in archives, the archive becomes a "folder". */
function partsOf(f) {
  if (!f.chain) return { parts: splitPath(f.path), arcAt: new Set() };
  const parts = splitPath(f.chain[0]);
  const arcAt = new Set();
  for (let i = 1; i < f.chain.length; i++) {
    arcAt.add(parts.length - 1);
    parts.push(...f.chain[i].split(/[\\/]+/).filter(Boolean));
  }
  return { parts, arcAt };
}

export function buildTree(groups, filter, sep, arcSep) {
  const root = newNode('', '');
  for (const g of groups) for (const f of g.files) {
    if (filter && !f.path.toLowerCase().includes(filter)) continue;
    const { parts, arcAt } = partsOf(f);
    const fname = parts.pop();
    let node = root, full = '', inArc = false;
    parts.forEach((p, i) => {
      full = full ? (inArc ? full + arcSep + p : joinName(full, p, sep)) : p;
      const key = (arcAt.has(i) ? '\u0001' : '') + p;
      if (!node.dirs.has(key)) {
        const nn = newNode(p, full);
        nn.archive = arcAt.has(i);
        nn.inArc = inArc;
        node.dirs.set(key, nn);
      }
      node = node.dirs.get(key);
      node.count++;
      node.size += g.size;
      if (arcAt.has(i)) inArc = true;
    });
    node.files.push({ f, g, name: fname });
  }
  compress(root, sep);
  return root;
}

/* Merges chains of single-child folders ("C:\Users\Mario" instead of three levels). */
function compress(node, sep) {
  const out = new Map();
  for (const c of node.dirs.values()) {
    let cur = c;
    while (cur.files.length === 0 && cur.dirs.size === 1 && !cur.archive && !cur.inArc) {
      const only = cur.dirs.values().next().value;
      if (only.inArc) break;
      only.name = joinName(cur.name, only.name, sep);
      cur = only;
    }
    compress(cur, sep);
    out.set((cur.archive ? '\u0001' : '') + cur.name, cur);
  }
  node.dirs = out;
}

export const byName = (a, b) => a.name.localeCompare(b.name);

/* A group's state relative to the selection: ['', ''] | ['sel', text] | ['arc', text] | ['danger', text] */
export function statusOf(g, selected, arcOk = false) {
  const disk = loose(g);
  let k = 0;
  for (const f of disk) if (selected.has(f.id)) k++;
  if (!k) return ['', ''];
  if (k === disk.length) {
    if (allowAllDisk(g, arcOk)) return ['arc', 'Kept only in archive'];
    return ['danger', disk.length === g.files.length ? 'All copies selected!' : 'All copies on disk selected!'];
  }
  return ['sel', `${k} of ${disk.length} to delete`];
}

/* Marks for deletion every copy on disk except those in keepIds. */
export function keepOnly(sel, g, keepIds) {
  for (const f of loose(g)) keepIds.has(f.id) ? sel.delete(f.id) : sel.add(f.id);
}

function under(path, prefix, sep) {
  const norm = s => (sep === '\\' ? s.toLowerCase() : s);
  let p = norm(prefix);
  if (!p.endsWith(sep)) p += sep;
  return norm(path).startsWith(p);
}

/* "Keep the copies here": for each group with copies both here and elsewhere, delete those elsewhere. */
export function keepDir(sel, groups, prefix, sep) {
  let n = 0;
  for (const g of groups) {
    const files = loose(g);
    const inside = files.filter(f => under(f.path, prefix, sep));
    if (!inside.length || inside.length === files.length) continue;
    keepOnly(sel, g, new Set(inside.map(f => f.id)));
    n++;
  }
  return n;
}

/* "Delete the copies here": selects the copies in this folder if one remains elsewhere
   (or, with arcOk, inside an archive). */
export function deleteDir(sel, groups, prefix, sep, arcOk = false, direct = false) {
  const norm = s => (sep === '\\' ? s.toLowerCase() : s);
  // direct: only the files directly in the folder (similar folders compare those)
  const isIn = direct ? p => norm(p.slice(0, Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\')))) === norm(prefix)
    : p => under(p, prefix, sep);
  let n = 0, skipped = 0;
  for (const g of groups) {
    const files = loose(g);
    const inside = files.filter(f => isIn(f.path));
    if (!inside.length) continue;
    const outside = files.filter(f => !isIn(f.path));
    if (!outside.length) {
      if (allowAllDisk(g, arcOk)) { inside.forEach(f => sel.add(f.id)); n++; } else skipped++;
      continue;
    }
    inside.forEach(f => sel.add(f.id));
    if (outside.every(f => sel.has(f.id))) sel.delete(outside[0].id);
    n++;
  }
  return [n, skipped];
}

export const STRATEGIES = {
  oldest: ['Keep the oldest copy', (a, b) => a.mtime - b.mtime],
  newest: ['Keep the newest copy', (a, b) => b.mtime - a.mtime],
  shortest: ['Keep the shortest path', (a, b) => a.path.length - b.path.length],
  longest: ['Keep the longest path', (a, b) => b.path.length - a.path.length],
  archived: ['Delete disk copies already in an archive', null],
};

/* Rank of a path in the preferred folders (first match wins, unmatched last). */
const rankOf = (path, prefer, sep) => {
  const i = prefer.findIndex(p => under(path, p, sep) || path === p);
  return i < 0 ? prefer.length : i;
};

/* Keeps one copy per group: the first in the preferred folders, ties broken by the rule.
   "archived" selects every disk copy of the groups that also have a copy in an archive. */
export function applyStrategy(sel, groups, key, prefer = [], sep = '/') {
  let n = 0;
  if (key === 'archived') {
    for (const g of groups) {
      if (!hasArc(g)) continue;
      loose(g).forEach(f => sel.add(f.id));
      n++;
    }
    return [n, 0];
  }
  const pick = STRATEGIES[key][1];
  const byDate = key === 'oldest' || key === 'newest';
  // equal dates (or equal path lengths) are common after a copy: a second rule decides, and is reported
  const tie = byDate ? (a, b) => a.path.length - b.path.length : (a, b) => a.mtime - b.mtime;
  let ties = 0;
  for (const g of groups) {
    const files = loose(g);
    if (files.length < 2) { files.forEach(f => sel.delete(f.id)); continue; }
    const rank = (a, b) => (rankOf(a.path, prefer, sep) - rankOf(b.path, prefer, sep)) || pick(a, b);
    const [best, next] = [...files].sort((a, b) => rank(a, b) || tie(a, b));
    if (rank(best, next) === 0) ties++;
    keepOnly(sel, g, new Set([best.id]));
    n++;
  }
  return [n, ties];
}

/* Effect of a selection change: files and bytes added/removed. */
export function diffSelection(before, after, sizeOf) {
  let add = 0, rem = 0, addB = 0, remB = 0;
  for (const id of after) if (!before.has(id)) { add++; addB += sizeOf(id); }
  for (const id of before) if (!after.has(id)) { rem++; remB += sizeOf(id); }
  return { add, rem, addB, remB };
}

/* CSV of the results: one row per copy (UTF-8; Excel wants the BOM added by saveText). */
export function toCsv(groups, selected) {
  const q = v => `"${String(v).replace(/"/g, '""')}"`;
  const rows = [['group', 'hash', 'size_bytes', 'path', 'in_archive', 'modified', 'selected_for_deletion']];
  for (const g of groups) for (const f of g.files) {
    rows.push([g.id, g.hash, g.size, f.path, f.chain ? 'yes' : 'no', new Date(f.mtime * 1000).toISOString(), selected.has(f.id) ? 'yes' : 'no']);
  }
  return rows.map(r => r.map(q).join(',')).join('\r\n');
}

/* Longest folder prefix shared by every path (cut at a separator, never inside a name). */
export function commonDir(paths, sep) {
  let pre = paths.length > 1 ? paths[0].slice(0, paths[0].lastIndexOf(sep) + 1) : '';
  for (const p of paths) while (pre && !p.startsWith(pre)) pre = pre.slice(0, pre.lastIndexOf(sep, pre.length - 2) + 1);
  return pre.length > 3 ? pre : '';            // a bare drive root ("C:\", "/") is not worth a line
}
