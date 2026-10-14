import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api.js';
import { fmtNum, fmtSize, nGroups, plural } from '../format.js';
import { commonDir } from '../tree.js';
import { Trash } from './Icons.jsx';

const VERB = { trash: 'moved to the Recycle Bin', quarantine: 'moved to quarantine', permanent: 'deleted' };

const MAX_GROUPS = 150;

/* Confirmation, mode choice and deletion report.
   groups (duplicates only): [{ keep: [file], del: [file] }] so the dialog shows what stays, not only what goes. */
export default function DeleteDialog({ cfg, ids, paths, groups, sep = '/', bytes, onClose, onDeleted, toast, arcKeep = false, similar = false, onElevate, onOpenQuarantine }) {
  const ref = useRef(null);
  const [mode, pickMode] = useState(cfg.trash ? 'trash' : 'quarantine');
  const [sure, setSure] = useState(false);       // permanent deletion must be confirmed in the dialog
  const setMode = m => { pickMode(m); setSure(false); };
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  useEffect(() => { ref.current.showModal(); }, []);
  const root = useMemo(() => commonDir(groups
    ? groups.flatMap(g => [...g.keep, ...g.del].map(f => f.path)) : paths, sep), [groups, paths, sep]);
  const rel = p => (p.startsWith(root) ? p.slice(root.length) : p);
  const forever = mode === 'permanent';

  async function run() {
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
        <h2>{!result.deleted.length ? 'Nothing was ' + VERB[result.mode]
          : result.errors.length ? `${fmtNum(result.deleted.length)} of ${fmtNum(result.deleted.length + result.errors.length)} files ${VERB[result.mode]}`
          : 'Done'}</h2>
        {result.deleted.length > 0 &&
          <p><span className="emerald strong">{fmtNum(result.deleted.length)} {result.deleted.length === 1 ? 'file' : 'files'} {VERB[result.mode]}</span> · {fmtSize(result.freed)} freed.</p>}
        {result.quarantine_dir && <p className="muted">Quarantine folder: <span className="mono">{result.quarantine_dir}</span></p>}
        {result.errors.length > 0 && <>
          <p className="amber">{fmtNum(result.errors.length)} files were left untouched:</p>
          <div className="list mono">{result.errors.map((e, i) => <div key={i}>{rel(e.path)} — {e.reason}</div>)}</div>
          {cfg.can_elevate && result.errors.some(e => e.reason.startsWith('Access denied')) &&
            <div className="banner amber">Some files are protected. Restart DupFinder as administrator and try again: the results and the selection are kept.
              <button className="btn ghost sm" onClick={onElevate}>Restart as administrator</button></div>}
        </>}
        <div className="dialog-btns">
          {result.mode === 'quarantine' && result.deleted.length > 0 && onOpenQuarantine &&
            <button className="btn ghost" onClick={() => { ref.current.close(); onOpenQuarantine(); }}>Open Quarantine</button>}
          <button className="btn primary" onClick={() => ref.current.close()}>Close</button>
        </div>
      </> : <>
        <h2>Delete {plural(ids.length, 'file')}?</h2>
        <p className="muted">{groups ? <>From {nGroups(groups.length)}, freeing</> : 'Frees'} about <strong className="emerald">{fmtSize(bytes)}</strong>. {similar
          ? 'At least one image of every group stays.'
          : arcKeep ? 'Every group keeps a copy on disk or inside an unchanged archive.' : 'Every group keeps at least one copy on disk.'}</p>
        {root && <p className="small muted">All paths below are in <span className="mono">{root}</span></p>}
        {groups ? <div className="list mono del-groups" aria-label="What each group keeps and deletes">
          {groups.slice(0, MAX_GROUPS).map((g, i) => <div className="del-group" key={i}>
            {g.keep.map(f => <div className={'del-row ' + (f.chain ? 'violet' : 'emerald')} key={f.id}>
              <b>{f.chain ? 'archive' : 'keep'}</b><span>{rel(f.path)}</span></div>)}
            {g.del.map(f => <div className="del-row crimson" key={f.id}><b>delete</b><span>{rel(f.path)}</span></div>)}
          </div>)}
          {groups.length > MAX_GROUPS && <div className="muted">…and {nGroups(groups.length - MAX_GROUPS)} more</div>}
        </div> : <div className="list mono">
          {paths.slice(0, 200).map((p, i) => <div key={i}>{rel(p)}</div>)}
          {paths.length > 200 && <div className="muted">…and {fmtNum(paths.length - 200)} more</div>}
        </div>}
        <div className="modes">
          <Mode value="trash" mode={mode} setMode={setMode} disabled={!cfg.trash} title="Move to the Recycle Bin"
            sub={cfg.trash ? 'You can restore them from the system Recycle Bin.' : 'Not available in this installation: choose quarantine to keep a way back.'} />
          <Mode value="quarantine" mode={mode} setMode={setMode} title="Move to quarantine"
            sub={<>Restore them any time from the Quarantine view. Stored in <span className="mono">{cfg.quarantine_dir}</span>.</>} />
          <Mode value="permanent" mode={mode} setMode={setMode} title="Delete permanently" sub="No way back: they skip the Recycle Bin and quarantine." danger />
        </div>
        {forever && <label className="check small danger">
          <input type="checkbox" checked={sure} onChange={e => setSure(e.target.checked)} />
          I understand these {plural(ids.length, 'file')} cannot be recovered</label>}
        <div className="dialog-btns">
          <button className="btn ghost" onClick={() => ref.current.close()}>Cancel</button>
          <button className="btn danger" disabled={busy || (forever && !sure)} onClick={run}><Trash size={14} />
            {busy ? 'Deleting…' : `${forever ? 'Delete forever' : mode === 'trash' ? 'Move to Recycle Bin' : 'Move to quarantine'}: ${plural(ids.length, 'file')}`}</button>
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
