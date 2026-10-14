import { useEffect, useRef, useState } from 'react';
import { api } from '../api.js';
import { fmtNum, fmtSize } from '../format.js';
import { Trash } from './Icons.jsx';

const VERB = { trash: 'moved to the Recycle Bin', quarantine: 'moved to quarantine', permanent: 'deleted' };

/* Confirmation, mode choice and deletion report. */
export default function DeleteDialog({ cfg, ids, paths, bytes, onClose, onDeleted, toast, arcKeep = false, similar = false, onElevate }) {
  const ref = useRef(null);
  const [mode, setMode] = useState(cfg.trash ? 'trash' : 'quarantine');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  useEffect(() => { ref.current.showModal(); }, []);

  async function run() {
    if (mode === 'permanent' && !confirm('The files will be deleted forever. Continue?')) return;
    setBusy(true);
    try {
      const r = await api('/api/delete', { ids, mode, arc_keep: arcKeep, similar });
      onDeleted(r.deleted);
      setResult(r);
    } catch (e) {
      toast(e.message, 5000);
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog ref={ref} className="dialog" onClose={onClose}>
      {result ? <>
        <h2>Done</h2>
        <p><span className="emerald strong">{fmtNum(result.deleted.length)} {result.deleted.length === 1 ? 'file' : 'files'} {VERB[result.mode]}</span> · {fmtSize(result.freed)} freed.</p>
        {result.quarantine_dir && <p className="muted">Quarantine folder: <span className="mono">{result.quarantine_dir}</span></p>}
        {result.errors.length > 0 && <>
          <p className="amber">{fmtNum(result.errors.length)} files were left untouched:</p>
          <div className="list mono">{result.errors.map((e, i) => <div key={i}>{e.path} — {e.reason}</div>)}</div>
          {cfg.can_elevate && result.errors.some(e => e.reason.startsWith('Access denied')) &&
            <div className="banner amber">Some files are protected. Restart DupFinder as administrator and try again: the results and the selection are kept.
              <button className="btn ghost sm" onClick={onElevate}>Restart as administrator</button></div>}
        </>}
        <div className="dialog-btns"><button className="btn primary" onClick={() => ref.current.close()}>Close</button></div>
      </> : <>
        <h2>Delete {fmtNum(ids.length)} {ids.length === 1 ? 'file' : 'files'}?</h2>
        <p className="muted">You will free about <strong className="emerald">{fmtSize(bytes)}</strong>. {similar
          ? 'At least one image of every group will stay.'
          : arcKeep ? 'Every group keeps a copy on disk or inside an unchanged archive.' : 'At least one copy of every group will stay on disk.'}</p>
        <div className="list mono">
          {paths.slice(0, 200).map((p, i) => <div key={i}>{p}</div>)}
          {paths.length > 200 && <div className="muted">…and {fmtNum(paths.length - 200)} more</div>}
        </div>
        <div className="modes">
          <Mode value="trash" mode={mode} setMode={setMode} disabled={!cfg.trash} title="Move to the Recycle Bin"
            sub={cfg.trash ? 'You can restore them from the system Recycle Bin.' : <>Not available: install send2trash with <code>pip install send2trash</code>.</>} />
          <Mode value="quarantine" mode={mode} setMode={setMode} title="Move to quarantine"
            sub={<><span className="mono">{cfg.quarantine_dir}</span>, keeping the folder structure.</>} />
          <Mode value="permanent" mode={mode} setMode={setMode} title="Delete permanently" sub="They cannot be recovered." danger />
        </div>
        <div className="dialog-btns">
          <button className="btn ghost" onClick={() => ref.current.close()}>Cancel</button>
          <button className="btn danger" disabled={busy} onClick={run}><Trash size={14} />{busy ? 'Deleting…' : `Delete ${fmtNum(ids.length)} ${ids.length === 1 ? 'file' : 'files'}`}</button>
        </div>
      </>}
    </dialog>
  );
}

function Mode({ value, mode, setMode, title, sub, disabled, danger }) {
  return (
    <label className={'mode' + (disabled ? ' disabled' : '') + (mode === value ? ' on' : '') + (danger ? ' danger' : '')}>
      <input type="radio" name="mode" value={value} checked={mode === value} disabled={disabled} onChange={() => setMode(value)} />
      <span><strong>{title}</strong><small>{sub}</small></span>
    </label>
  );
}
