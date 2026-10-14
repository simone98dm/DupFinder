import { useMemo, useState } from 'react';
import { api } from '../api.js';
import { fmtDate, fmtNum, fmtSize } from '../format.js';
import { Caret, FolderFill, Open } from '../components/Icons.jsx';

const CATS = [
  ['Images', 'cyan', 'jpg jpeg png gif bmp webp tif tiff heic raw cr2 nef arw dng svg psd'],
  ['Video', 'violet', 'mp4 mkv mov avi wmv m4v mpg mpeg webm 3gp'],
  ['Audio', 'emerald', 'mp3 wav flac aac m4a ogg wma opus'],
  ['Documents', 'amber', 'pdf doc docx xls xlsx ppt pptx odt ods txt rtf md csv epub'],
  ['Archives', 'violet', 'zip 7z rar gz tar bz2 xz iso'],
  ['Code & data', 'muted', 'py js ts jsx html css json xml sql java c cpp h cs go rs php sh db sqlite'],
];
const catOf = ext => CATS.find(([, , list]) => list.split(' ').includes(ext.replace('.', '')))?.[0] || 'Other';

/* Statistics from the last scan: types, years, folders, largest and oldest files. */
export default function Inventory({ res, toast }) {
  const inv = res?.inventory;
  const [tab, setTab] = useState('largest');
  const cats = useMemo(() => {
    const m = new Map();
    for (const [ext, n, b] of inv?.ext ?? []) {
      const c = catOf(ext);
      const e = m.get(c) || [0, 0];
      m.set(c, [e[0] + n, e[1] + b]);
    }
    return [...m.entries()].sort((a, b) => b[1][1] - a[1][1]);
  }, [inv]);
  if (!inv?.files) return <div className="panel empty">Run a scan to see the inventory: file types, years, folder sizes, the largest and the oldest files.</div>;
  const reveal = path => api('/api/reveal_path', { path }).catch(e => toast(e.message));
  const years = inv.years.filter(([y]) => y > 0);
  const maxYear = Math.max(1, ...years.map(y => y[2]));
  const oldest = inv.oldest[0];

  return (
    <>
      <div className="metrics">
        <Metric label="Files" value={fmtNum(inv.files)} sub={`in ${fmtNum(res.roots.length)} ${res.roots.length === 1 ? 'root' : 'roots'}`} />
        <Metric label="Total size" value={fmtSize(inv.bytes)} sub="cloud-only files excluded" />
        <Metric label="File types" value={fmtNum(inv.ext.length)} sub="distinct extensions" cls="amber" />
        <Metric label="Oldest file" value={oldest ? new Date(oldest.mtime * 1000).getFullYear() : '—'} sub={oldest ? oldest.path.split(/[\\/]/).pop() : ''} cls="emerald" />
      </div>

      <div className="grid-2">
        <section className="panel">
          <h3 className="panel-title">Space by type</h3>
          <div className="bars">
            {cats.map(([c, [n, b]]) => (
              <Bar key={c} label={c} value={b} max={inv.bytes} sub={`${fmtNum(n)} files`} cls={CATS.find(x => x[0] === c)?.[1] || 'muted'} />
            ))}
          </div>
          <details className="more">
            <summary>Top extensions</summary>
            <table className="tbl">
              <thead><tr><th>Extension</th><th className="num">Files</th><th className="num">Size</th></tr></thead>
              <tbody>{inv.ext.slice(0, 40).map(([e, n, b]) => <tr key={e}><td className="mono">{e}</td><td className="num">{fmtNum(n)}</td><td className="num">{fmtSize(b)}</td></tr>)}</tbody>
            </table>
          </details>
        </section>

        <section className="panel">
          <h3 className="panel-title">Space by year of last change</h3>
          <div className="years" role="list">
            {years.map(([y, n, b]) => (
              <div key={y} className="year" role="listitem" title={`${y}: ${fmtNum(n)} files, ${fmtSize(b)}`}>
                <div className="year-bar"><div style={{ height: Math.max(2, (b / maxYear) * 100) + '%' }} /></div>
                <span className="mono">{String(y).slice(2)}</span>
              </div>
            ))}
          </div>
          <p className="hint">Hover a bar for the details. These are modification dates: copying a file may reset them.</p>
        </section>
      </div>

      <section className="panel">
        <h3 className="panel-title">Space by folder</h3>
        <FolderTree folders={inv.folders} reveal={reveal} />
      </section>

      <section className="panel">
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === 'largest'} onClick={() => setTab('largest')}>Largest files</button>
          <button role="tab" aria-selected={tab === 'oldest'} onClick={() => setTab('oldest')}>Oldest files</button>
        </div>
        <table className="tbl">
          <thead><tr><th>File</th><th className="num">Size</th><th className="num">Modified</th><th /></tr></thead>
          <tbody>{(tab === 'largest' ? inv.largest : inv.oldest).map(f => (
            <tr key={f.path}>
              <td className="mono ellip" title={f.path}>{f.path}</td>
              <td className="num">{fmtSize(f.size)}</td>
              <td className="num">{fmtDate(f.mtime)}</td>
              <td><button className="icon-btn" onClick={() => reveal(f.path)} title="Show in folder" aria-label="Show in folder"><Open size={14} /></button></td>
            </tr>
          ))}</tbody>
        </table>
      </section>
    </>
  );
}

function FolderTree({ folders, reveal }) {
  const children = useMemo(() => {
    const m = new Map();
    const byPath = new Set(folders.map(f => f[0]));
    for (const f of folders) {
      const parent = f[4];
      if (parent && !byPath.has(parent)) continue;
      if (!m.has(parent)) m.set(parent, []);
      m.get(parent).push(f);
    }
    for (const l of m.values()) l.sort((a, b) => b[2] - a[2]);
    return m;
  }, [folders]);
  const tops = children.get('') || [];
  const total = tops.reduce((s, f) => s + f[2], 0) || 1;
  return <div className="ftree">{tops.map(f => <FolderRow key={f[0]} f={f} kidsOf={children} total={total} reveal={reveal} startOpen />)}</div>;
}

function FolderRow({ f, kidsOf, total, reveal, startOpen = false }) {
  const [open, setOpen] = useState(startOpen);
  const [path, n, b, depth] = f;
  const kids = kidsOf.get(path) || [];
  const name = depth === 0 ? path : path.split(/[\\/]/).pop();
  return (
    <div className="frow">
      <div className="frow-line" style={{ paddingLeft: depth * 16 }}>
        <button className="icon-btn" onClick={() => setOpen(!open)} disabled={!kids.length} aria-expanded={open} aria-label={open ? 'Collapse' : 'Expand'}>
          {kids.length > 0 && <Caret size={12} className={'caret' + (open ? ' open' : '')} />}
        </button>
        <FolderFill size={14} className="dir-ico" />
        <span className="mono ellip grow" title={path}>{name}</span>
        <span className="frow-bar"><i style={{ width: Math.max(1, (b / total) * 100) + '%' }} /></span>
        <span className="mono num w-80">{fmtSize(b)}</span>
        <span className="mono num muted w-80">{fmtNum(n)} files</span>
        <button className="icon-btn" onClick={() => reveal(path)} title="Show in folder" aria-label="Show in folder"><Open size={14} /></button>
      </div>
      {open && kids.map(k => <FolderRow key={k[0]} f={k} kidsOf={kidsOf} total={total} reveal={reveal} />)}
    </div>
  );
}

function Bar({ label, value, max, sub, cls }) {
  const pct = max ? (value / max) * 100 : 0;
  return (
    <div className="bar-row">
      <span className="bar-label">{label}</span>
      <span className="bar-track"><i className={'bg-' + cls} style={{ width: Math.max(0.5, pct) + '%' }} /></span>
      <span className="mono num w-80">{fmtSize(value)}</span>
      <span className="mono num muted w-80">{sub}</span>
    </div>
  );
}

export function Metric({ label, value, sub, cls = '' }) {
  return (
    <div className={'metric ' + cls}>
      <div className="metric-l"><span>{label}</span>{cls && <i className={'sw sm ' + cls} />}</div>
      <div className="metric-v">{value}</div>
      <div className="metric-s ellip" title={typeof sub === 'string' ? sub : undefined}>{sub}</div>
    </div>
  );
}
