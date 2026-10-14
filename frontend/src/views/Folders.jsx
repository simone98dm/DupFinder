import { useState } from 'react';
import { api } from '../api.js';
import { fmtNum, fmtSize } from '../format.js';
import { Archive, FolderFill, Open } from '../components/Icons.jsx';

/* Folders whose files are (wholly or mostly) also in another folder: whole backup copies. */
export default function Folders({ res, arcSep, act, toast }) {
  const [onlyFull, setOnlyFull] = useState(false);
  const rows = (res?.folders ?? []).filter(r => !onlyFull || r.shared === r.total);
  if (!res) return <div className="panel empty">Run a scan to find folders that are copies of other folders.</div>;
  if (!res.folders.length) return <div className="panel empty">No folder shares at least half of its files with another one.</div>;
  const reveal = p => api('/api/reveal_path', { path: p.split(arcSep)[0] }).catch(e => toast(e.message));

  return (
    <>
      <div className="toolbar">
        <div className="tool-group">
          <label className="check"><input type="checkbox" checked={onlyFull} onChange={e => setOnlyFull(e.target.checked)} />
            Only folders fully contained in another</label>
        </div>
        <div className="legend small muted">Compares the files directly inside each folder (subfolders count on their own).</div>
      </div>
      <div className="tree">
        {rows.map(r => {
          const full = r.shared === r.total;
          return (
            <div key={r.dir + '|' + r.other} className="fold-row">
              <div className="fold-main">
                <div className="fold-line">
                  {r.in_archive ? <Archive size={14} className="violet" /> : <FolderFill size={14} className="dir-ico" />}
                  <span className="mono ellip" title={r.dir}>{r.dir}</span>
                  <button className="icon-btn" onClick={() => reveal(r.dir)} title="Show in folder" aria-label="Show in folder"><Open size={14} /></button>
                </div>
                <div className="fold-line small muted">
                  <span className={full ? 'badge emerald' : 'badge amber'}>{full ? 'Fully contained' : `${Math.round((r.shared / r.total) * 100)}% contained`}</span>
                  <span>{fmtNum(r.shared)} of {fmtNum(r.total)} files also in</span>
                  {r.other_in_archive ? <Archive size={14} className="violet" /> : <FolderFill size={14} className="dir-ico" />}
                  <span className="mono ellip" title={r.other}>{r.other}</span>
                  <button className="icon-btn" onClick={() => reveal(r.other)} title="Show in folder" aria-label="Show in folder"><Open size={14} /></button>
                </div>
              </div>
              <span className="recov">{fmtSize(r.bytes)}</span>
              {!r.in_archive && <button className="btn drop xs" onClick={() => act.deleteDir(r.dir, true)}
                title="Mark the copies in this folder for deletion (only where a copy remains elsewhere)">Delete copies here</button>}
            </div>
          );
        })}
      </div>
    </>
  );
}
