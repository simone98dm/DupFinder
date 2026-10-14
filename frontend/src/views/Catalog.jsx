import { useCallback, useEffect, useState } from 'react';
import { api } from '../api.js';
import { fmtDate, fmtNum, fmtSize, plural } from '../format.js';
import { Archive, Open, Play, Search } from '../components/Icons.jsx';
import { FolderField, FoldersField, JobError, JobProgress, lines, useJob } from '../components/Job.jsx';
import { Metric } from './Inventory.jsx';

/* SQLite catalog: incremental zips of unique files, search, restore and integrity checks. */
export default function Catalog({ cfg, toast }) {
  const [sum, setSum] = useState(null);
  const s = cfg.settings || {};
  const [sources, setSources] = useState(s.archive_sources || '');
  const [dest, setDest] = useState(s.archive_dest || '');
  const reload = useCallback(() => api('/api/catalog').then(setSum).catch(e => toast(e.message)), [toast]);
  const arc = useJob('archive', reload);
  const ver = useJob('verify', reload);
  useEffect(() => { reload(); }, [reload]);

  function startArchive() {
    if (!lines(sources).length || !dest.trim()) { toast('Choose the folders to archive and where the archives go.'); return; }
    api('/api/settings', { archive_sources: sources, archive_dest: dest }).catch(() => {});
    arc.start({ sources: lines(sources), dest }).catch(e => toast(e.message, 5000));
  }
  const r = arc.st.state === 'done' ? arc.st.result : null;

  return (
    <>
      {sum && <div className="metrics">
        <Metric label="Archives" value={fmtNum(sum.archives.length)} sub={`${fmtNum(sum.archives.filter(a => !a.current).length)} not found (disk disconnected?)`} cls="violet" />
        <Metric label="Files catalogued" value={fmtNum(sum.files)} sub="unique content" />
        <Metric label="Original size" value={fmtSize(sum.bytes)} sub="before compression" cls="emerald" />
        <Metric label="Last check" value={sum.archives.some(a => a.verify_status === 'damaged') ? 'Problems' : 'OK'}
          sub={sum.archives.length ? fmtDate(Math.min(...sum.archives.map(a => a.verified || 0))) + ' (oldest)' : '—'}
          cls={sum.archives.some(a => a.verify_status === 'damaged') ? 'crimson' : 'emerald'} />
      </div>}

      <section className="panel">
        <h2 className="panel-title">New incremental archive</h2>
        <p className="hint">Only files whose content is not in the catalog yet go into the new zip (duplicates are stored once).
          The zip is read back and checked before being recorded. The original files are not touched:
          to free space, scan them afterwards with "Copies in archives count as kept".</p>
        <div className="scan-grid">
          <div className="field">
            <label className="label-caps" htmlFor="asrc">Folders to archive <span className="hint">one per line</span></label>
            <FoldersField id="asrc" value={sources} onChange={setSources} placeholder={'D:\\Photos\\2019'} />
          </div>
          <div className="field">
            <label className="label-caps" htmlFor="adest">Where the archives go</label>
            <FolderField id="adest" value={dest} onChange={setDest} placeholder={'E:\\Archives'} />
            <span className="hint">Prefer another disk: the zip is named DupFinder_&lt;date&gt;.zip.</span>
          </div>
        </div>
        <div className="scan-foot">
          <span className="grow" />
          <button className="btn primary" disabled={arc.running} onClick={startArchive}><Play size={14} />Create archive</button>
        </div>
        <JobProgress st={arc.st} onCancel={arc.cancel} />
        <JobError st={arc.st} />
        {r && <div className={'banner ' + (r.files ? 'emerald' : '')}>
          {r.files ? <>Archived <b>{plural(r.files, 'file')}</b> ({fmtSize(r.bytes)}) in <span className="mono">{r.archive}</span>. </> : 'Nothing new to archive. '}
          {r.already > 0 && <>{fmtNum(r.already)} files were already in the catalog or duplicated. </>}
          {r.errors.length > 0 && <span className="amber">{fmtNum(r.errors.length)} files could not be read.</span>}
        </div>}
        {r?.errors.length > 0 && <div className="list mono">{r.errors.map((e, i) => <div key={i}>{e.path} — {e.error}</div>)}</div>}
      </section>

      <SearchRestore toast={toast} />

      <section className="panel">
        <div className="panel-head">
          <h2 className="panel-title">Archives</h2>
          <button className="btn ghost sm" disabled={ver.running || !sum?.archives.length} onClick={() => ver.start({}).catch(e => toast(e.message))}>Verify all</button>
        </div>
        <JobProgress st={ver.st} onCancel={ver.cancel} />
        <JobError st={ver.st} />
        {!sum?.archives.length ? <p className="muted">No archive yet.</p> : (
          <table className="tbl">
            <thead><tr><th>Archive</th><th className="num">Created</th><th className="num">Files</th><th className="num">Size</th><th>State</th><th /></tr></thead>
            <tbody>{sum.archives.map(a => (
              <tr key={a.id}>
                <td className="mono ellip" title={a.current || a.path}><Archive size={12} className="violet" /> {a.current || a.path}
                  {a.current && a.current !== a.path && <span className="badge">moved</span>}</td>
                <td className="num">{fmtDate(a.created)}</td>
                <td className="num">{fmtNum(a.files)}</td>
                <td className="num">{fmtSize(a.bytes)}</td>
                <td>{!a.current ? <span className="badge amber">not found</span>
                  : a.verify_status === 'damaged' ? <span className="badge crimson">damaged</span>
                    : <span className="badge emerald">ok</span>}</td>
                <td className="nowrap">
                  {a.current && <button className="icon-btn" onClick={() => api('/api/reveal_path', { path: a.current }).catch(e => toast(e.message))} title="Show in folder" aria-label="Show in folder"><Open size={14} /></button>}
                  <button className="btn text xs" disabled={ver.running || !a.current} onClick={() => ver.start({ ids: [a.id] }).catch(e => toast(e.message))}>Verify</button>
                  <button className="btn text xs" onClick={() => {
                    if (confirm('Remove this archive from the catalog? The zip file is not deleted, but its files will count as not archived.'))
                      api('/api/catalog/forget', { id: a.id }).then(reload).catch(e => toast(e.message));
                  }}>Forget</button>
                </td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </section>
    </>
  );
}

function SearchRestore({ toast }) {
  const [q, setQ] = useState('');
  const [rows, setRows] = useState(null);
  const [sel, setSel] = useState(() => new Set());
  const [target, setTarget] = useState('');
  const job = useJob('restore');
  useEffect(() => {
    if (!q.trim()) { setRows(null); return; }
    const t = setTimeout(() => api('/api/catalog/search?q=' + encodeURIComponent(q)).then(r => { setRows(r.results); setSel(new Set()); }).catch(e => toast(e.message)), 300);
    return () => clearTimeout(t);
  }, [q, toast]);
  const toggle = (id, on) => setSel(s => { const n = new Set(s); on ? n.add(id) : n.delete(id); return n; });
  const res = job.st.state === 'done' ? job.st.result : null;

  return (
    <section className="panel">
      <h2 className="panel-title">Search and restore</h2>
      <div className="search wide">
        <Search size={14} />
        <input type="search" placeholder="Part of the original path or name, or a BLAKE2b hash…" value={q} onChange={e => setQ(e.target.value)} aria-label="Search the catalog" />
      </div>
      {rows && (rows.length === 0 ? <p className="muted">Nothing found.</p> : <>
        <table className="tbl">
          <thead><tr><th><input type="checkbox" aria-label="Select all" checked={sel.size === rows.length} onChange={e => setSel(e.target.checked ? new Set(rows.map(r => r.id)) : new Set())} /></th>
            <th>Original path</th><th className="num">Size</th><th className="num">Modified</th><th>Archive</th></tr></thead>
          <tbody>{rows.map(r => (
            <tr key={r.id}>
              <td><input type="checkbox" checked={sel.has(r.id)} onChange={e => toggle(r.id, e.target.checked)} aria-label={'Select ' + r.original} /></td>
              <td className="mono ellip" title={r.original}>{r.original}</td>
              <td className="num">{fmtSize(r.size)}</td>
              <td className="num">{r.mtime ? fmtDate(r.mtime) : ''}</td>
              <td className="mono ellip muted" title={r.archive}>{r.archive.split(/[\\/]/).pop()}</td>
            </tr>
          ))}</tbody>
        </table>
        {rows.length >= 500 && <p className="hint">Only the first 500 results are shown: refine the search.</p>}
        <div className="restore-row">
          <button className="btn primary sm" disabled={!sel.size || job.running} onClick={() => job.start({ ids: [...sel] }).catch(e => toast(e.message))}>
            Restore {fmtNum(sel.size)} to the original place</button>
          <span className="muted small">or into</span>
          <FolderField value={target} onChange={setTarget} placeholder="another folder" />
          <button className="btn ghost sm" disabled={!sel.size || !target.trim() || job.running} onClick={() => job.start({ ids: [...sel], target }).catch(e => toast(e.message))}>Restore there</button>
        </div>
      </>)}
      <JobProgress st={job.st} onCancel={job.cancel} />
      <JobError st={job.st} />
      {res && <div className={'banner ' + (res.errors.length ? 'amber' : 'emerald')}>
        Restored {plural(res.restored.length, 'file')}{res.errors.length ? `, ${fmtNum(res.errors.length)} not restored:` : '.'}
      </div>}
      {res?.errors.length > 0 && <div className="list mono">{res.errors.map((e, i) => <div key={i}>{e.path} — {e.error}</div>)}</div>}
    </section>
  );
}
