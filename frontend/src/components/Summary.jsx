import { useState } from 'react';
import { Alert } from './Icons.jsx';
import { fmtNum, fmtSize, plural } from '../format.js';
import { allowAllDisk, loose } from '../tree.js';

/* One line: what was found, what can be freed, how much of it is selected; then the scan notices. */
export default function Summary({ meta, groups, selBytes, arcOk = false }) {
  let files = 0, wasted = 0;
  // with arcOk a copy inside an archive is enough: every disk copy of those groups is recoverable
  for (const g of groups) { files += g.files.length; wasted += g.size * Math.max(loose(g).length - (allowAllDisk(g, arcOk) ? 0 : 1), 0); }
  const selPct = wasted ? Math.min(100, (selBytes / wasted) * 100) : 0;
  const secs = meta.elapsed || 0;

  return (
    <section className="summary" aria-label="Scan summary">
      <div className="sumline">
        <span><b className="amber">{fmtNum(groups.length)}</b> {groups.length === 1 ? 'group' : 'groups'} of identical files</span>
        <span><b>{fmtNum(files)}</b> copies</span>
        <span className="emerald" title={arcOk ? 'Keeping one copy per group; a copy in an archive counts' : 'Keeping one copy per group on disk'}>
          <b>{fmtSize(wasted)}</b> recoverable</span>
        <span className="muted">{fmtNum(meta.files_seen || 0)} files examined in {secs.toFixed(1)} s
          {meta.cache_hits > 0 && <span title="Hashes reused from earlier scans (files not changed)">, {fmtNum(meta.cache_hits)} from cache</span>}</span>
        {wasted > 0 && <span className="sum-sel">
          <span className="emerald"><b>{fmtSize(selBytes)}</b> selected to free</span>
          <span className="track mini" role="progressbar" aria-label="Share of the recoverable space selected"
            aria-valuenow={Math.round(selPct)} aria-valuemin={0} aria-valuemax={100}><span className="fill emerald" style={{ width: selPct + '%' }} /></span>
        </span>}
      </div>
      <Notices meta={meta} />
    </section>
  );
}

function Notices({ meta }) {
  const [open, setOpen] = useState(false);
  const n = [];
  if (meta.arc_scanned) n.push(<span key="a" className="notice"><i className="sw violet" /><span>Archives scanned: <b>{fmtNum(meta.arc_scanned)}</b> <span className="muted">({plural(meta.arc_entries, 'file')} inside{meta.arc_cached ? `, ${fmtNum(meta.arc_cached)} from the cache` : ''}; reported only)</span></span></span>);
  if (meta.arc_no7z) n.push(<span key="7" className="notice amber"><Alert size={14} className="amber" />{fmtNum(meta.arc_no7z)} 7z/RAR archives skipped: 7-Zip is not installed</span>);
  if (meta.error_count) n.push(<span key="e" className="notice dim"><i className="sw sm crimson" />{fmtNum(meta.error_count)} {meta.error_count === 1 ? 'item' : 'items'} not read (permissions, in use, password or damaged)</span>);
  if (meta.placeholders) n.push(<span key="p" className="notice dim">{fmtNum(meta.placeholders)} cloud-only files skipped</span>);
  if (meta.hardlinks) n.push(<span key="h" className="notice dim">{fmtNum(meta.hardlinks)} hardlinks ignored</span>);
  if (!n.length) return null;
  return (
    <div className="notices">
      <div className="notice-row">
        <div className="notice-items">{n}</div>
        {meta.error_count > 0 && <button className="btn link" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? 'Hide log' : 'Log details'}</button>}
      </div>
      {open && <ul>{meta.errors.map((e, i) => <li key={i} className="mono">{e.path} — {e.error}</li>)}</ul>}
    </div>
  );
}
