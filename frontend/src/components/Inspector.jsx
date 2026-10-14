import { useContext } from 'react';
import { Copy, Shield, Tick } from './Icons.jsx';
import { TreeCtx } from './Tree.jsx';
import Preview from './Preview.jsx';
import { fmtNum, fmtSize } from '../format.js';
import { loose, statusOf } from '../tree.js';

/* Right panel: details and verification of the clicked group. */
export default function Inspector({ g, toast }) {
  const { selected, arcOk } = useContext(TreeCtx);
  if (!g) return (
    <aside className="inspector">
      <div className="panel insp-empty">
        <Shield size={22} className="cyan" />
        <p>Click a file to see the details of its group of identical copies.</p>
      </div>
    </aside>
  );
  const disk = loose(g);
  const sel = disk.filter(f => selected.has(f.id)).length;
  const [cls] = statusOf(g, selected, arcOk);
  const name = (disk[0] ?? g.files[0]).path.split(/[\\/]/).pop();
  const copyHash = () => navigator.clipboard.writeText(g.hash).then(() => toast('Hash copied.'), () => toast('Cannot copy: select the hash by hand.'));
  return (
    <aside className="inspector">
      <div className="panel insp">
        <div className="insp-head">
          <div style={{ minWidth: 0 }}>
            <h2 className="insp-title">Group details</h2>
            <span className="mono ellip" title={name}>{name}</span>
          </div>
          <span className="badge emerald"><Tick size={12} />Identical content</span>
        </div>

        {disk[0] && <Preview id={disk[0].id} path={disk[0].path} className="insp-preview" />}

        <div className="insp-hash">
          <div className="insp-hash-l">
            <span>BLAKE2b hash:</span>
            <button className="btn link" onClick={copyHash}><Copy size={14} />copy</button>
          </div>
          <div className="hashbox">{g.hash}</div>
          <div className="exact">
            <span style={{ fontFamily: 'var(--sans)' }} className="muted">Exact size:</span>
            <span><b>{fmtNum(g.size)} bytes</b> <span className="muted">({fmtSize(g.size)})</span></span>
          </div>
        </div>

        <p className="insp-counts">
          <span><b>{fmtNum(disk.length)}</b> on disk, <b className="emerald">{fmtNum(disk.length - sel)}</b> kept</span>
          {g.files.length > disk.length && <span className="violet"><b>{fmtNum(g.files.length - disk.length)}</b> in archives (read-only)</span>}
          {sel > 0 && <span><b className="crimson">{fmtNum(sel)}</b> to delete, <b className="emerald">{fmtSize(g.size * sel)}</b> freed</span>}
        </p>

        {cls === 'arc'
          ? <div className="guard arc"><Shield size={16} /><div><strong>Kept only inside an archive:</strong> deletion goes ahead only if the archive is still exactly the one scanned.</div></div>
          : cls === 'danger'
          ? <div className="guard danger"><Shield size={16} /><div><strong>Every copy on disk is selected:</strong> keep at least one to delete the others.</div></div>
          : <div className="guard"><Shield size={16} /><div><strong>Copy protection active:</strong> at least one copy on disk always stays. Copies inside archives are never touched.</div></div>}
      </div>

    </aside>
  );
}
