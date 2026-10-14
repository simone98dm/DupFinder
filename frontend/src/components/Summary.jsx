import { useState } from 'react';
import { Alert } from './Icons.jsx';
import { fmtNum, fmtSize } from '../format.js';
import { allowAllDisk, loose } from '../tree.js';

/* Metric cards, segmented bar (selected / still recoverable) and the one-line notice banner. */
export default function Summary({ meta, groups, selBytes, arcOk = false }) {
  let files = 0, wasted = 0;
  // with arcOk a copy inside an archive is enough: every disk copy of those groups is recoverable
  for (const g of groups) { files += g.files.length; wasted += g.size * Math.max(loose(g).length - (allowAllDisk(g, arcOk) ? 0 : 1), 0); }
  const selPct = wasted ? Math.min(100, (selBytes / wasted) * 100) : 0;
  const secs = meta.elapsed || 0;

  return (
    <section className="summary">
      <div className="metrics">
        <Metric label="Files examined" value={fmtNum(meta.files_seen || 0)}
          sub={`in ${secs.toFixed(1)}s` + (secs ? ` (${fmtNum(Math.round((meta.files_seen || 0) / secs))} files/s)` : '')} />
        <Metric label="Duplicate groups" value={fmtNum(groups.length)} unit="groups" sub="identical content" cls="amber" />
        <Metric label="Files involved" value={fmtNum(files)} unit="files" sub="total copies" />
        <Metric label="Recoverable space" value={fmtSize(wasted)} sub={arcOk ? 'keeping one copy per group (archives count)' : 'keeping one copy per group'} cls="emerald" />
      </div>

      {wasted > 0 && <div className="segbar">
        <div className="seg-legend">
          <span className="crimson"><i className="sw crimson" />Selected for deletion:<b>{fmtSize(selBytes)} ({selPct.toFixed(0)}%)</b></span>
          <span className="amber"><i className="sw amber" />Still recoverable:<b>{fmtSize(Math.max(wasted - selBytes, 0))} ({(100 - selPct).toFixed(0)}%)</b></span>
          <span className="total">Total candidates: <b>{fmtSize(wasted)}</b></span>
        </div>
        <div className="track seg">
          <div className="fill crimson" style={{ width: selPct + '%' }} />
          <div className="fill amber" style={{ width: (100 - selPct) + '%' }} />
        </div>
      </div>}

      <Notices meta={meta} />
    </section>
  );
}

function Metric({ label, value, unit, sub, cls = '' }) {
  return (
    <div className={'metric ' + cls}>
      <div className="metric-l"><span>{label}</span>{cls && <i className={'sw sm ' + cls} />}</div>
      <div className="metric-v">{value}{unit && <small> {unit}</small>}</div>
      <div className="metric-s">{sub}</div>
    </div>
  );
}

function Notices({ meta }) {
  const [open, setOpen] = useState(false);
  const n = [];
  if (meta.arc_scanned) n.push(<span key="a" className="notice"><i className="sw violet" /><span>Archives scanned: <b>{fmtNum(meta.arc_scanned)}</b> <span className="muted">({fmtNum(meta.arc_entries)} files inside{meta.arc_cached ? `, ${fmtNum(meta.arc_cached)} from the cache` : ''}; reported only)</span></span></span>);
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
