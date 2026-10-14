import { useEffect, useRef, useState } from 'react';
import { api } from '../api.js';
import { fmtNum, fmtSize } from '../format.js';
import { Archive } from './Icons.jsx';
import { FolderField, JobError, JobProgress, useJob } from './Job.jsx';

const AFTER = {
  keep: ['Keep the archive', 'Nothing is removed: you can delete it later.'],
  quarantine: ['Move the archive to quarantine', 'Only if every file was extracted or skipped without errors.'],
  trash: ['Move the archive to the Recycle Bin', 'Only if every file was extracted or skipped without errors.'],
};

/* Extracts an archive found by the scan, optionally skipping the files already on disk. */
export default function ExtractDialog({ cfg, archive, onClose, onChanged }) {
  const ref = useRef(null);
  const [plan, setPlan] = useState(null);
  const [planErr, setPlanErr] = useState('');
  const [dest, setDest] = useState('');
  const [skip, setSkip] = useState(true);
  const [after, setAfter] = useState('quarantine');
  const [started, setStarted] = useState(false);     // an earlier extraction's outcome is not shown
  const job = useJob('extract', s => { if (s.result) onChanged(); });
  useEffect(() => { ref.current.showModal(); }, []);

  // the plan is recomputed when the destination changes (free space depends on the disk)
  useEffect(() => {
    const t = setTimeout(() => api('/api/extract/plan', { archive, dest: dest || null })
      .then(p => { setPlan(p); setPlanErr(''); if (!dest) setDest(p.dest); })
      .catch(e => setPlanErr(e.message)), dest ? 400 : 0);
    return () => clearTimeout(t);
  }, [archive, dest]);   // eslint-disable-line react-hooks/exhaustive-deps

  const need = plan ? (skip ? plan.need : plan.need_all) : 0;
  const short = plan && plan.free !== null && plan.free < need + plan.margin;
  const res = job.st.result;
  const finished = started && (job.st.state === 'done' || (job.st.state === 'cancelled' && res));

  return (
    <dialog ref={ref} className="dialog" onClose={onClose} onCancel={e => job.running && e.preventDefault()}>
      <h2><Archive size={18} className="violet" /> Extract archive</h2>
      <p className="mono small ellip" title={archive}>{archive}</p>

      {finished && res ? <Outcome res={res} /> : <>
        {planErr && <div className="banner crimson" role="alert">{planErr}</div>}
        {plan && <>
          <div className="kv-grid">
            <span>Files in the archive</span><b className="mono">{fmtNum(plan.files)} · {fmtSize(plan.bytes)}</b>
            <span>Already on disk (identical)</span><b className="mono amber">{fmtNum(plan.duplicates)} · {fmtSize(plan.duplicate_bytes)}</b>
            {plan.encrypted > 0 && <><span>Password protected</span><b className="mono crimson">{fmtNum(plan.encrypted)} (not extracted)</b></>}
            {plan.unsafe > 0 && <><span>Unsafe names</span><b className="mono crimson">{fmtNum(plan.unsafe)} (not extracted)</b></>}
            <span>Space needed</span><b className={'mono ' + (short ? 'crimson' : 'emerald')}>{fmtSize(need)}</b>
            <span>Free on that disk</span><b className="mono">{plan.free === null ? 'unknown' : fmtSize(plan.free)}</b>
          </div>
          {short && <div className="banner crimson" role="alert">Not enough free space: free {fmtSize(need + plan.margin - plan.free)} or choose another folder.</div>}
        </>}

        <div className="field">
          <label className="label-caps" htmlFor="xdest">Extract to</label>
          <FolderField id="xdest" value={dest} onChange={setDest} />
          <span className="hint">Files whose names are already taken get a " (1)" suffix: nothing is overwritten.</span>
        </div>
        <label className="check"><input type="checkbox" checked={skip} onChange={e => setSkip(e.target.checked)} disabled={job.running} />
          Skip the files that already have an identical copy on disk</label>

        <div className="modes">
          {Object.entries(AFTER).map(([k, [title, sub]]) => (
            <label key={k} className={'mode' + (after === k ? ' on' : '') + (k === 'trash' && !cfg.trash ? ' disabled' : '')}>
              <input type="radio" name="after" checked={after === k} disabled={job.running || (k === 'trash' && !cfg.trash)} onChange={() => setAfter(k)} />
              <span><strong>{title}</strong><small>{sub}</small></span>
            </label>
          ))}
        </div>

        <JobProgress st={job.st} onCancel={job.cancel} />
        {started && <JobError st={job.st} />}
      </>}

      <div className="dialog-btns">
        {finished
          ? <button className="btn primary" onClick={() => ref.current.close()}>Close</button>
          : <>
            <button className="btn ghost" disabled={job.running} onClick={() => ref.current.close()}>Cancel</button>
            <button className="btn primary" disabled={!plan || short || job.running || !!planErr}
              onClick={() => { setStarted(true); job.start({ archive, dest, skip_dups: skip, after }).catch(e => setPlanErr(e.message)); }}>
              {job.running ? 'Extracting…' : 'Extract'}</button>
          </>}
      </div>
    </dialog>
  );
}

function Outcome({ res }) {
  return (
    <>
      {res.stopped
        ? <div className={'banner ' + (res.complete ? 'amber' : 'crimson')} role="alert">{res.stopped}</div>
        : <div className="banner emerald">Extraction complete.</div>}
      <div className="kv-grid">
        <span>Extracted</span><b className="mono emerald">{fmtNum(res.extracted)} · {fmtSize(res.extracted_bytes)}</b>
        <span>Skipped (already on disk)</span><b className="mono amber">{fmtNum(res.skipped)} · {fmtSize(res.skipped_bytes)}</b>
        {res.renamed > 0 && <><span>Renamed (name taken)</span><b className="mono">{fmtNum(res.renamed)}</b></>}
        <span>Folder</span><b className="mono ellip" title={res.dest}>{res.dest}</b>
        <span>Archive</span><b className="mono">{{ kept: 'kept', quarantine: 'moved to quarantine', trash: 'moved to the Recycle Bin' }[res.archive_action]}</b>
      </div>
      {res.errors.length > 0 && <>
        <p className="amber">{fmtNum(res.errors.length)} files were not extracted (the archive was kept):</p>
        <div className="list mono">{res.errors.map((e, i) => <div key={i}>{e.path} — {e.error}</div>)}</div>
      </>}
      <p className="muted small">The scan results no longer match the disk: scan again to refresh them.</p>
    </>
  );
}
