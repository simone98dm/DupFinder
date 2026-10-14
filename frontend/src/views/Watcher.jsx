import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { fmtDate, fmtSize } from '../format.js';
import { Open } from '../components/Icons.jsx';
import { FoldersField, lines } from '../components/Job.jsx';

const KIND = {
  archived: ['violet', 'Archived'], copy: ['amber', 'Copy on disk'], new: ['emerald', 'Not archived'], error: ['crimson', 'Error'],
};

/* Inbox folders: every new file is checked against the catalog and the files hashed by earlier scans. */
export default function Watcher({ watch, onChange, toast }) {
  const [folders, setFolders] = useState(watch.folders.join('\n'));
  useEffect(() => { setFolders(watch.folders.join('\n')); }, [watch.folders.join('\n')]);   // eslint-disable-line react-hooks/exhaustive-deps

  const save = enabled => api('/api/watch', { folders: lines(folders), enabled }).then(onChange).catch(e => toast(e.message, 5000));
  const reveal = p => api('/api/reveal_path', { path: p }).catch(e => toast(e.message));
  const events = [...watch.events].reverse();

  return (
    <>
      <section className="panel">
        <div className="scan-grid">
          <div className="field">
            <label className="label-caps" htmlFor="wf">Inbox folders <span className="hint">one per line</span></label>
            <FoldersField id="wf" value={folders} onChange={setFolders} placeholder={'C:\\Users\\Mario\\Downloads'} />
          </div>
          <div className="field">
            <span className="label-caps">How it works</span>
            <p className="hint">Every few seconds the folders are checked. When a file stops changing, its content is compared with
              the catalog (<span className="violet">already archived</span>) and with the files hashed by earlier scans
              (<span className="amber">a copy exists on disk</span>); otherwise it is <span className="emerald">not archived</span>.
              Only files hashed before are known: those archived, and the duplicate candidates of the scans.
              The watcher runs while DupFinder is open and starts again with it.</p>
          </div>
        </div>
        <div className="scan-foot">
          <span className={'small ' + (watch.enabled ? 'emerald' : 'muted')}>{watch.enabled ? '● Watching' : '○ Stopped'}</span>
          <span className="grow" />
          {watch.enabled && <button className="btn ghost" onClick={() => save(false)}>Stop</button>}
          <button className="btn primary" onClick={() => save(true)}>{watch.enabled ? 'Save folders' : 'Start watching'}</button>
        </div>
      </section>

      <section className="panel">
        <h2 className="panel-title">Events</h2>
        {events.length === 0 ? <p className="muted">No file checked yet.</p> : (
          <table className="tbl">
            <thead><tr><th>Time</th><th>File</th><th>Result</th><th /></tr></thead>
            <tbody>{events.map(e => (
              <tr key={e.id}>
                <td className="num nowrap">{fmtDate(e.time)}</td>
                <td className="mono ellip" title={e.path}>{e.path.split(/[\\/]/).pop()}{e.size ? <span className="muted"> · {fmtSize(e.size)}</span> : null}</td>
                <td className="ellip" title={e.where || e.text}>
                  <span className={'badge ' + KIND[e.kind][0]}>{KIND[e.kind][1]}</span> <span className="small muted">{e.where || e.text}</span>
                </td>
                <td>{e.path && <button className="icon-btn" onClick={() => reveal(e.path)} title="Show in folder" aria-label="Show in folder"><Open size={14} /></button>}</td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </section>
    </>
  );
}
