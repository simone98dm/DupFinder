import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api.js';
import { fmtDate, fmtNum, fmtSize } from '../format.js';
import { Open, Play, Trash } from '../components/Icons.jsx';
import { JobError, JobProgress, useJob } from '../components/Job.jsx';
import Preview from '../components/Preview.jsx';

/* Similar images (resized, recompressed copies) among the images of the last scan. */
export default function Images({ cfg, res, toast, onDelete }) {
  const [groups, setGroups] = useState([]);
  const [sel, setSel] = useState(() => new Set());
  const load = useCallback(() => api('/api/similar').then(r => setGroups(r.groups)).catch(e => toast(e.message)), [toast]);
  const job = useJob('similar', s => { if (s.state === 'done') { setSel(new Set()); load(); } });
  useEffect(() => { load(); }, [load]);

  const byId = useMemo(() => new Map(groups.flatMap(g => g.files.map(f => [f.id, f]))), [groups]);
  const selBytes = [...sel].reduce((s, id) => s + (byId.get(id)?.size || 0), 0);
  const fullGroups = groups.filter(g => g.files.every(f => sel.has(f.id))).length;
  const toggle = (id, on) => setSel(s => { const n = new Set(s); on ? n.add(id) : n.delete(id); return n; });
  const keepBest = () => setSel(new Set(groups.flatMap(g => g.files.slice(1).map(f => f.id))));

  if (!cfg.pillow) return <div className="panel empty">This feature needs Pillow: install it with <code>pip install Pillow</code> and restart DupFinder.</div>;
  if (!res) return <div className="panel empty">Run a scan first: the images to compare come from the scanned folders.</div>;

  return (
    <>
      <div className="toolbar">
        <div className="tool-group">
          <button className="btn primary sm" disabled={job.running || !res.images} onClick={() => job.start({}).catch(e => toast(e.message))}>
            <Play size={12} />{groups.length ? 'Search again' : 'Find similar images'}</button>
          <span className="small muted">{fmtNum(res.images)} images in the last scan</span>
          {groups.length > 0 && <>
            <span className="vsep" />
            <button className="btn ghost sm" onClick={keepBest}>Keep the best of each group</button>
          </>}
        </div>
        <div className="legend small muted">Best = highest resolution, then largest file. Similar is not identical: check before deleting.</div>
      </div>
      <JobProgress st={job.st} onCancel={job.cancel} />
      <JobError st={job.st} />
      {job.st.state === 'done' && job.st.result?.error_count > 0 &&
        <div className="banner">{fmtNum(job.st.result.error_count)} images could not be read (damaged or unsupported format).</div>}

      {groups.length === 0 && job.st.state !== 'running' &&
        <div className="panel empty">{job.st.state === 'done' ? 'No similar images found.' : 'Press "Find similar images" to compare them (hashes are cached for the next time).'}</div>}

      {groups.map(g => (
        <section key={g.id} className="panel sim-group">
          <div className="small muted">{g.files.length} similar images</div>
          <div className="thumbs">
            {g.files.map((f, i) => {
              const on = sel.has(f.id);
              return (
                <div key={f.id} className={'thumb' + (on ? ' marked' : i === 0 ? ' best' : '')}>
                  <Preview id={f.id} path={f.path} set="sim" className="thumb-img" />
                  <label className="thumb-meta">
                    <input type="checkbox" checked={on} onChange={e => toggle(f.id, e.target.checked)} aria-label={'Delete ' + f.path} />
                    <span className="grow">
                      <span className="mono ellip block" title={f.path}>{f.path.split(/[\\/]/).pop()}</span>
                      <span className="mono small muted" title={'Modified ' + fmtDate(f.mtime)}>{f.w}×{f.h} · {fmtSize(f.size)}</span>
                      {f.identical && <span className="small amber block">identical copy of another one here</span>}
                    </span>
                    {i === 0 && !on && <span className="badge emerald">best</span>}
                    {on && <span className="badge crimson">to delete</span>}
                  </label>
                  <button className="icon-btn" onClick={() => api('/api/reveal', { id: f.id, set: 'sim' }).catch(e => toast(e.message))} title="Show in folder" aria-label="Show in folder"><Open size={14} /></button>
                </div>
              );
            })}
          </div>
        </section>
      ))}

      {groups.length > 0 && (
        <footer className="actionbar sticky">
          <div className="actionbar-left">
            <span className="actionbar-ico"><Trash size={16} /></span>
            <span className="actionbar-count">{fmtNum(sel.size)} images selected</span>
            {sel.size > 0 && <span className="free-badge">{fmtSize(selBytes)} to free</span>}
          </div>
          <div className={'actionbar-rule' + (fullGroups ? ' amber' : '')}>
            {fullGroups ? `In ${fullGroups} groups every image is selected: keep at least one.` : 'At least one image of every group always stays.'}
          </div>
          <div className="actionbar-right">
            <button className="btn text" disabled={!sel.size} onClick={() => setSel(new Set())}>Deselect all</button>
            <button className="btn danger" disabled={!sel.size || fullGroups > 0}
              onClick={() => onDelete([...sel], selBytes, [...sel].map(id => byId.get(id)?.path), ids => {
                const del = new Set(ids);
                setSel(s => new Set([...s].filter(x => !del.has(x))));
                load();
              })}>
              <Trash size={16} />Delete {fmtNum(sel.size)} images…</button>
          </div>
        </footer>
      )}
    </>
  );
}
