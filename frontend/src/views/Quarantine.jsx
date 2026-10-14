import { useCallback, useEffect, useState } from 'react';
import { api } from '../api.js';
import { fmtNum, fmtSize, plural } from '../format.js';
import { Caret, Open } from '../components/Icons.jsx';

/* Files moved to quarantine: put them back where they were, or delete them for good. */
export default function Quarantine({ cfg, toast }) {
  const [sessions, setSessions] = useState(null);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const reload = useCallback(() => api('/api/quarantine').then(r => setSessions(r.sessions)).catch(e => toast(e.message)), [toast]);
  useEffect(() => { reload(); }, [reload]);

  async function run(path, body, msg) {
    setBusy(true);
    try {
      const r = await api(path, body);
      setReport({ ...r, msg });
    } catch (e) {
      toast(e.message, 5000);
    } finally {
      setBusy(false);
      reload();
    }
  }

  if (!sessions) return null;
  return (
    <>
      <p className="muted small">Quarantine folder: <span className="mono">{cfg.quarantine_dir}</span>. Each deletion in quarantine mode is a session.</p>
      {report && <div className={'banner ' + (report.errors.length ? 'amber' : 'emerald')}>
        {report.msg === 'restore' ? `Restored ${plural(report.restored.length, 'file')}.` : `Deleted for good: ${fmtSize(report.freed)} freed.`}
        {report.errors.length > 0 && ` ${fmtNum(report.errors.length)} problems:`}
        {report.errors.length > 0 && <div className="list mono">{report.errors.map((e, i) => <div key={i}>{e.path} — {e.error}</div>)}</div>}
      </div>}
      {sessions.length === 0 && <div className="panel empty">The quarantine is empty.</div>}
      {sessions.map(s => <Session key={s.id} s={s} busy={busy} run={run} toast={toast} />)}
    </>
  );
}

function Session({ s, busy, run, toast }) {
  const [open, setOpen] = useState(false);
  const blocked = s.files.filter(f => f.exists).length;
  return (
    <section className="panel">
      <div className="panel-head">
        <button className="icon-btn" onClick={() => setOpen(!open)} aria-expanded={open} aria-label={open ? 'Collapse' : 'Expand'}>
          <Caret size={14} className={'caret' + (open ? ' open' : '')} /></button>
        <h2 className="panel-title grow">{s.name.replace('_', ' ').replace(/-(\d\d)-(\d\d)$/, ':$1:$2')}
          <span className="muted small"> · {plural(s.files.length, 'file')} · {fmtSize(s.bytes)}</span></h2>
        <button className="icon-btn" onClick={() => api('/api/reveal_path', { path: s.dir }).catch(e => toast(e.message))} title="Show in folder" aria-label="Show in folder"><Open size={14} /></button>
        <button className="btn keep-em sm" disabled={busy} onClick={() => run('/api/quarantine/restore', { id: s.id }, 'restore')}>Restore all</button>
        <button className="btn drop sm" disabled={busy} onClick={() => {
          if (confirm(`Delete these ${s.files.length} files for good? They cannot be recovered.`)) run('/api/quarantine/purge', { id: s.id }, 'purge');
        }}>Delete for good</button>
      </div>
      {blocked > 0 && <p className="small amber">{fmtNum(blocked)} files have a new file at their original place: they will not be overwritten.</p>}
      {open && <table className="tbl">
        <thead><tr><th>Original place</th><th className="num">Size</th><th /></tr></thead>
        <tbody>{s.files.map(f => (
          <tr key={f.stored}>
            <td className="mono ellip" title={f.original}>{f.original}{f.exists && <span className="badge amber">place taken</span>}</td>
            <td className="num">{fmtSize(f.size)}</td>
            <td><button className="btn text xs" disabled={busy || f.exists} onClick={() => run('/api/quarantine/restore', { id: s.id, stored: [f.stored] }, 'restore')}>Restore</button></td>
          </tr>
        ))}</tbody>
      </table>}
    </section>
  );
}
