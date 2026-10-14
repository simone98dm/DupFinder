import { createContext, memo, useContext, useEffect, useMemo, useState } from 'react';
import { Archive, Caret, File, FolderFill, Lock, Open } from './Icons.jsx';
import { fmtDate, fmtNum, fmtSize } from '../format.js';
import { byName, commonDir, loose, statusOf } from '../tree.js';

/* State shared by the tree: selection, commands and the "expand/collapse all" signal. */
export const TreeCtx = createContext(null);

const EXPAND_LIMIT = 4000;   // beyond this, "Expand all" stops so the browser does not freeze

export default function Tree({ root, empty }) {
  if (empty) return <div className="panel empty">No duplicate files found.</div>;
  const dirs = [...root.dirs.values()].sort(byName);
  if (!dirs.length) return <div className="panel empty">No files match the filter.</div>;
  return (
    <div className="tree" role="tree" aria-label="Duplicates by folder" tabIndex={0} onFocus={enterTree} onKeyDown={moveInTree}>
      {dirs.map(d => <Dir key={d.full} node={d} defaultOpen={dirs.length <= 3} lone={dirs.length === 1} />)}
    </div>
  );
}

/* Keyboard: the tree is one tab stop; arrows move between visible rows, Home/End jump. */
function enterTree(e) {
  if (e.target === e.currentTarget && !e.currentTarget.contains(e.relatedTarget))
    e.currentTarget.querySelector('[data-row]')?.focus();
}
function moveInTree(e) {
  if (e.defaultPrevented) return;              // the row already handled it (open/close)
  const rows = [...e.currentTarget.querySelectorAll('[data-row]')];
  const i = rows.indexOf(e.target);
  if (i < 0) return;
  const go = j => { e.preventDefault(); rows[Math.max(0, Math.min(rows.length - 1, j))].focus(); };
  if (e.key === 'ArrowDown') go(i + 1);
  else if (e.key === 'ArrowUp') go(i - 1);
  else if (e.key === 'Home') go(0);
  else if (e.key === 'End') go(rows.length - 1);
  else if (e.key === 'ArrowLeft') {
    const parent = e.target.parentElement.closest('[data-row]');
    if (parent) { e.preventDefault(); parent.focus(); }
  }
}
/* Keys a row handles itself: Enter/Space toggle, Right opens, Left closes. */
function rowKeys(e, open, toggle) {
  if (e.target !== e.currentTarget) return;
  if (e.key === 'Enter' || e.key === ' ' || (e.key === 'ArrowRight' && !open) || (e.key === 'ArrowLeft' && open)) {
    e.preventDefault();
    toggle();
  }
}

/* Open/closed state of a node: follows "Expand all"/"Collapse all" up to EXPAND_LIMIT nodes. */
function useOpen(defaultOpen) {
  const { expand } = useContext(TreeCtx);
  const [open, setOpen] = useState(() => defaultOpen || (expand.mode === 'expand' && expand.budget.n++ < EXPAND_LIMIT));
  useEffect(() => {
    if (expand.v) setOpen(expand.mode === 'expand' && expand.budget.n++ < EXPAND_LIMIT);
  }, [expand]);
  return [open, setOpen];
}

/* Ids of the copies listed under a folder node, at any depth. */
function subtreeIds(node, out = []) {
  for (const x of node.files) out.push(x.f.id);
  for (const d of node.dirs.values()) subtreeIds(d, out);
  return out;
}

const Dir = memo(function Dir({ node, defaultOpen, lone = false }) {
  const { act, selected } = useContext(TreeCtx);
  const [open, setOpen] = useOpen(defaultOpen);
  const ids = useMemo(() => subtreeIds(node), [node]);
  let marked = 0;
  for (const id of ids) if (selected.has(id)) marked++;
  // a lone scan root holds every copy: "keep here / delete here" would do nothing there
  const plain = !node.archive && !node.inArc && !lone;
  return (
    <div className={'node dir' + (node.archive ? ' arc' : '')} role="treeitem" aria-expanded={open} aria-label={`${node.name}, ${node.count} ${node.count === 1 ? 'copy' : 'copies'}${marked ? `, ${marked} to delete` : ''}`}
      tabIndex={-1} data-row onKeyDown={e => rowKeys(e, open, () => setOpen(!open))}>
      <div className="row" onClick={() => setOpen(!open)}>
        <Caret size={14} className={'caret' + (open ? ' open' : '')} />
        {node.archive ? <Archive className="violet" /> : <FolderFill className="dir-ico" />}
        <span className="name" title={node.full}>{node.name}</span>
        {node.archive && <span className="badge violet">archive</span>}
        <span className="meta">· {fmtNum(node.count)} {node.count === 1 ? 'copy' : 'copies'} ({fmtSize(node.size)})</span>
        {marked > 0 && <span className="marked-count">{fmtNum(marked)} to delete</span>}
        <span className="grow" />
        {node.archive && !node.inArc && <span className="row-actions" onClick={e => e.stopPropagation()}>
          <button className="btn arc xs" onClick={() => act.extract(node.full)}
            title="Extract this archive, skipping the files already on disk, then optionally remove it">Extract…</button>
        </span>}
        {plain && <span className="row-actions" onClick={e => e.stopPropagation()}>
          <button className="btn keep-em xs" onClick={() => act.keepDir(node.full)}
            title="For each group with a copy here, mark the copies elsewhere for deletion">Keep here</button>
          <button className="btn drop xs" onClick={() => act.deleteDir(node.full)}
            title="Mark the copies in this folder for deletion, if one exists elsewhere">Delete here</button>
        </span>}
      </div>
      {open && <div className="children" role="group">
        {[...node.dirs.values()].sort(byName).map(c => <Dir key={(c.archive ? 'a:' : 'd:') + c.full} node={c} />)}
        {[...node.files].sort(byName).map(x => <FileRow key={x.f.id} item={x} />)}
      </div>}
    </div>
  );
});

function FileRow({ item: { f, g, name } }) {
  const { selected, focus, act, arcOk } = useContext(TreeCtx);
  const [open, setOpen] = useState(false);
  const [cls, txt] = statusOf(g, selected, arcOk);
  const disk = loose(g).length;
  const nArc = g.files.length - disk;
  const toggle = () => { setOpen(!open); act.focus(g.id); };
  const keys = e => {
    if (e.target === e.currentTarget && e.key === 'Delete' && !f.chain) { e.preventDefault(); act.toggle(f.id, !selected.has(f.id)); return; }
    rowKeys(e, open, toggle);
  };
  return (
    <div className={'node file' + (open ? ' open' : '') + (focus === g.id ? ' focused' : '')} role="treeitem" aria-expanded={open}
      aria-label={`${name}, ${g.files.length} copies${txt ? ', ' + txt : ''}`} tabIndex={-1} data-row onKeyDown={keys}>
      <div className="row" onClick={toggle}>
        <Caret size={14} className={'caret' + (open ? ' open' : '')} />
        {f.chain ? <Archive className="violet" /> : open && <File className="cyan" />}
        <span className="name" title={f.path}>{name}</span>
        {open
          ? <><span className="file-size">{fmtSize(g.size)}</span><span className="badge amber">{g.files.length} copies detected</span></>
          : <span className="badge">{g.files.length} copies · {fmtSize(g.size)}</span>}
        {f.chain ? <span className="badge violet">in archive</span>
          : nArc > 0 && <span className="badge violet" title={`The same content is also inside ${nArc === 1 ? 'an archive' : nArc + ' archives'}`}>also in archive</span>}
        <span className="row-right">
          {txt && <span className={'status ' + cls}>{txt}</span>}
          {open ? <span className="hash-short">BLAKE2b: {g.hash.slice(0, 8)}…{g.hash.slice(-8)}</span>
            : !txt && disk > 1 && <span className="recov">{fmtSize(g.size * (disk - 1))} recoverable</span>}
        </span>
      </div>
      {open && <Copies f={f} g={g} />}
    </div>
  );
}

/* Path without the folders every copy shares (base), so what tells the copies apart comes first;
   the folder part shrinks before the file name. The full path stays in the tooltip. */
function PathText({ p, base = '' }) {
  const { arcSep } = useContext(TreeCtx);
  const a = p.lastIndexOf('/'), b = p.lastIndexOf('\\'), c = p.lastIndexOf(arcSep);
  const i = Math.max(a, b, c >= 0 ? c + arcSep.length - 1 : -1);
  const from = base && p.startsWith(base) && base.length <= i + 1 ? base.length : 0;
  return <div className="copy-path" title={p}><span className="pre">{from ? '…' + base.slice(-1) : ''}{p.slice(from, i + 1)}</span><span className="fn">{p.slice(i + 1)}</span></div>;
}

/* The copies of a group (the clicked one first). Copies in archives have no checkbox. */
export function Copies({ f, g }) {
  const { selected, act } = useContext(TreeCtx);
  const list = f ? [f, ...g.files.filter(x => x.id !== f.id)] : g.files;
  const base = commonDir(g.files.map(x => x.path), g.files[0].path.includes('\\') ? '\\' : '/');
  return (
    <div className="copies">
      {list.map(x => {
        const self = f && x.id === f.id ? <span className="cyan"> · this file</span> : null;
        if (x.chain) return (
          <div key={x.id} className="copy inarc">
            <div className="copy-main">
              <span className="copy-ico" title="Inside an archive: cannot be deleted"><Archive size={16} /></span>
              <div className="copy-text">
                <PathText p={x.path} base={base} />
                <div className="copy-meta">In archive: {fmtDate(x.mtime)}{self}</div>
              </div>
            </div>
            <div className="copy-actions">
              <span className="badge violet"><Lock size={12} />In archive (read-only)</span>
              {x.chain.length === 2 && <button className="btn arc xs" onClick={() => act.extract(x.chain[0])}
                title="Extract this archive, skipping the files already on disk">Extract archive…</button>}
              <button className="icon-btn violet" onClick={() => act.reveal(x.id)} title="Show the archive in its folder" aria-label="Show the archive in its folder"><Open size={14} /></button>
            </div>
          </div>
        );
        const on = selected.has(x.id);
        return (
          <div key={x.id} className={'copy' + (on ? ' marked' : '')}>
            <label className="copy-main">
              <input type="checkbox" checked={on} onChange={e => act.toggle(x.id, e.target.checked)} aria-label={'Delete ' + x.path} />
              <div className="copy-text">
                <PathText p={x.path} base={base} />
                <div className="copy-meta">Modified: {fmtDate(x.mtime)}{self}</div>
              </div>
            </label>
            <div className="copy-actions">
              {on ? <span className="badge crimson">-{fmtSize(g.size)} to delete</span> : <span className="badge emerald">Kept</span>}
              <button className={'btn xs ' + (on ? 'ghost' : 'keep-em')} onClick={() => act.keepOnly(x.id)}>Keep only this one</button>
              <button className="icon-btn" onClick={() => act.reveal(x.id)} title="Show in folder" aria-label="Show in folder"><Open size={14} /></button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
