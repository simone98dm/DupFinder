import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, saveText } from './api.js';
import { fmtNum, fmtSize, nGroups } from './format.js';
import {
  allowAllDisk, applyStrategy, buildTree, deleteDir, diffSelection, keepDir, keepOnly, loose, STRATEGIES, toCsv,
} from './tree.js';
import Sidebar, { NAV } from './components/Sidebar.jsx';
import ScanPanel, { useScanForm } from './components/ScanPanel.jsx';
import Progress from './components/Progress.jsx';
import Summary from './components/Summary.jsx';
import Tree, { TreeCtx } from './components/Tree.jsx';
import Inspector from './components/Inspector.jsx';
import DeleteDialog from './components/DeleteDialog.jsx';
import ExtractDialog from './components/ExtractDialog.jsx';
import { lines } from './components/Job.jsx';
import { Alert, Check, Search, Trash } from './components/Icons.jsx';
import Inventory from './views/Inventory.jsx';
import Folders from './views/Folders.jsx';
import Images from './views/Images.jsx';
import Catalog from './views/Catalog.jsx';
import Quarantine from './views/Quarantine.jsx';
import Watcher from './views/Watcher.jsx';

const INTRO = {
  dedup: <>Found by <strong>CONTENT</strong>, never by name: same size → quick hash (first and last 64 KB) → full BLAKE2b.
    Files inside archives (ZIP/7z/RAR) are only reported; an archive can be extracted to get rid of the copies it holds.</>,
  folders: <>Folders whose files are, wholly or mostly, also in another folder: typically old backup copies that can go in one step.</>,
  images: <>Images that look the same even if resized or recompressed (64-bit difference hash). Unlike duplicates, they are <strong>not identical</strong>.</>,
  inventory: <>What the scanned folders contain: file types, years, space per folder, the largest and the oldest files.</>,
  catalog: <>Local zip archives holding only files not archived yet, with a SQLite catalog of original paths: search, restore, integrity checks.
    Archives on external disks are found again even if the drive letter changes.</>,
  quarantine: <>Files deleted in quarantine mode, kept with their folder structure: put them back where they were or delete them for good.</>,
  watch: <>Drop files in an inbox folder and DupFinder tells you whether they are already archived or already on disk.</>,
};

export default function App() {
  const [cfg, setCfg] = useState(null);
  const [fatal, setFatal] = useState('');
  const [view, setView] = useState('dedup');
  const [st, setSt] = useState({ state: 'idle' });
  const [res, setRes] = useState(null);             // results of /api/results
  const [stale, setStale] = useState(false);        // files changed on disk (extraction): rescan advised
  const [selected, setSelected] = useState(() => new Set());
  const [focus, setFocus] = useState(null);         // id of the group shown on the right
  const [filter, setFilter] = useState('');
  const [filterText, setFilterText] = useState('');
  const [strategy, setStrategy] = useState('');
  const [prefer, setPrefer] = useState('');
  const [showRules, setShowRules] = useState(false);
  const [arcOk, setArcOk] = useState(false);
  const [expand, setExpand] = useState({ mode: '', v: 0, budget: { n: 0 } });
  const [del, setDel] = useState(null);             // delete dialog: { ids, bytes, paths, similar, done }
  const [extractArc, setExtractArc] = useState(null);
  const [watch, setWatch] = useState({ folders: [], enabled: false, events: [], seq: 0 });
  const [watchSeen, setWatchSeen] = useState(0);
  const [toastMsg, setToastMsg] = useState(null);
  const [showScan, setShowScan] = useState(true);
  const [form, setForm, scanBody] = useScanForm(cfg);
  const toastTimer = useRef(null);

  const toast = useCallback((msg, ms = 2600) => {
    setToastMsg(msg);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToastMsg(null), ms);
  }, []);

  /* ---------- config, scan start and status ---------- */
  useEffect(() => {
    api('/api/config').then(c => {
      setCfg(c);
      setArcOk(!!c.settings.arc_keep);
      setPrefer(c.settings.prefer || '');
      setWatchSeen(c.settings.watch_seen || 0);
    }).then(() => api('/api/state')).then(setSt)
      .catch(e => setFatal('Cannot reach DupFinder: ' + e.message));
  }, []);

  const running = st.state === 'running';
  useEffect(() => {
    if (!running) return;
    const t = setTimeout(() => api('/api/state').then(setSt).catch(() => setSt(s => ({ ...s }))), 500);
    return () => clearTimeout(t);
  }, [st, running]);

  const loadResults = useCallback(() => api('/api/results').then(r => {
    setRes(r);
    setSelected(new Set(r.selection));
    setShowScan(false);
    setStale(false);
  }).catch(e => toast(e.message, 5000)), [toast]);

  useEffect(() => {
    if (st.state === 'done' && (!res || res.session !== st.session)) loadResults();
    if (st.state === 'cancelled') toast('Scan cancelled.');
    if (st.state === 'error') toast('Error during the scan: ' + st.message, 6000);
  }, [st.state, st.session]);   // eslint-disable-line react-hooks/exhaustive-deps

  async function startScan() {
    const body = scanBody();
    if (!body.paths.length) { setView('dedup'); setShowScan(true); toast('Enter at least one folder to scan.'); return; }
    try {
      await api('/api/scan', body);
      setRes(null); setSelected(new Set()); setFocus(null); setStale(false);
      setView(v => (v === 'dedup' || v === 'folders' || v === 'inventory' ? v : 'dedup'));
      setSt(await api('/api/state'));
    } catch (e) { toast(e.message, 4000); }
  }
  const cancelScan = () => api('/api/cancel', {}).catch(e => toast(e.message));
  const elevate = () => api('/api/admin/restart', {})
    .then(() => toast('Restarting as administrator… this window will close.', 8000))
    .catch(e => toast(e.message, 5000));

  /* ---------- selection is saved with the session (it survives a restart) ---------- */
  const lastSaved = useRef(null);
  useEffect(() => {
    if (!res) return;
    const key = res.session + ':' + [...selected].join(',');
    if (lastSaved.current === null) { lastSaved.current = key; return; }   // just loaded: nothing to save
    if (key === lastSaved.current) return;
    const t = setTimeout(() => {
      lastSaved.current = key;
      api('/api/selection', { session: res.session, ids: [...selected] }).catch(() => {});
    }, 700);
    return () => clearTimeout(t);
  }, [selected, res]);

  /* ---------- watcher: polled for the badge and the events ---------- */
  useEffect(() => {
    let live = true;
    const poll = () => api('/api/watch').then(w => live && setWatch(w)).catch(() => {});
    poll();
    const t = setInterval(poll, 4000);
    return () => { live = false; clearInterval(t); };
  }, []);
  useEffect(() => {
    if (view === 'watch' && watch.seq > watchSeen) {
      setWatchSeen(watch.seq);
      api('/api/settings', { watch_seen: watch.seq }).catch(() => {});
    }
  }, [view, watch.seq, watchSeen]);

  /* ---------- indexes and tree ---------- */
  const groups = res?.groups ?? [];
  const sep = res?.sep ?? '/';
  const arcSep = res?.arc_sep ?? ' › ';
  const { fileById, groupById } = useMemo(() => {
    const fileById = new Map(), groupById = new Map();
    for (const g of groups) { groupById.set(g.id, g); for (const f of g.files) fileById.set(f.id, { f, g }); }
    return { fileById, groupById };
  }, [groups]);

  useEffect(() => { const t = setTimeout(() => setFilterText(filter.trim().toLowerCase()), 200); return () => clearTimeout(t); }, [filter]);
  const root = useMemo(() => buildTree(groups, filterText, sep, arcSep), [groups, filterText, sep, arcSep]);

  /* ---------- selection ---------- */
  const { selBytes, fullGroups } = useMemo(() => {
    let selBytes = 0;
    const perGroup = new Map();
    for (const id of selected) {
      const e = fileById.get(id);
      if (!e) continue;
      selBytes += e.g.size;
      perGroup.set(e.g.id, (perGroup.get(e.g.id) || 0) + 1);
    }
    let fullGroups = 0;
    for (const [gid, k] of perGroup) {
      const g = groupById.get(gid);
      if (k === loose(g).length && !allowAllDisk(g, arcOk)) fullGroups++;
    }
    return { selBytes, fullGroups };
  }, [selected, fileById, groupById, arcOk]);

  // Selection rules work on a copy of the Set: the result is computed right away, then saved.
  const change = fn => { const s = new Set(selected); const out = fn(s); setSelected(s); return out; };
  const act = {
    toggle: (id, on) => change(s => (on ? s.add(id) : s.delete(id))),
    keepOnly: id => change(s => keepOnly(s, fileById.get(id).g, new Set([id]))),
    focus: setFocus,
    reveal: id => api('/api/reveal', { id }).catch(e => toast(e.message)),
    extract: path => setExtractArc(path),
    keepDir: prefix => {
      const n = change(s => keepDir(s, groups, prefix, sep));
      toast(n ? `${nGroups(n)} updated: kept the copies in this folder.` : 'No group has copies both here and elsewhere.');
    },
    deleteDir: (prefix, direct = false) => {
      const [n, skipped] = change(s => deleteDir(s, groups, prefix, sep, arcOk, direct));
      toast(`${nGroups(n)} updated.` + (skipped ? ` ${nGroups(skipped)} skipped because all their copies on disk are in this folder.` : ''), 4000);
    },
  };

  const preferList = useMemo(() => lines(prefer), [prefer]);
  const preview = useMemo(() => {
    if (!strategy || !groups.length) return null;
    const after = new Set(selected);
    applyStrategy(after, groups, strategy, preferList, sep);
    return diffSelection(selected, after, id => fileById.get(id)?.g.size || 0);
  }, [strategy, preferList, groups, selected, sep, fileById]);

  function setArcKeep(v) {
    setArcOk(v);
    api('/api/settings', { arc_keep: v }).catch(() => {});
  }
  function runStrategy() {
    if (!strategy) { toast('Choose a rule first.'); return; }
    if (strategy === 'archived' && !arcOk) setArcKeep(true);
    const n = change(s => applyStrategy(s, groups, strategy, preferList, sep));
    toast(`Selection applied to ${nGroups(n)}. Review it before deleting.`);
  }
  function savePrefer(v) {
    setPrefer(v);
    api('/api/settings', { prefer: v }).catch(() => {});
  }
  async function exportCsv() {
    try {
      const p = await saveText(`dupfinder-${new Date().toISOString().slice(0, 10)}.csv`, toCsv(groups, selected));
      if (p) toast('Exported: ' + p, 4000);
    } catch (e) { toast(e.message, 5000); }
  }

  function onDeleted(ids) {
    const d = new Set(ids);
    setRes(r => ({ ...r, groups: r.groups.map(g => ({ ...g, files: g.files.filter(f => !d.has(f.id)) })).filter(g => g.files.length > 1) }));
    setSelected(prev => new Set([...prev].filter(id => !d.has(id))));
  }
  const openDelete = () => setDel({
    ids: [...selected], bytes: selBytes, similar: false, done: onDeleted,
    paths: [...selected].map(id => fileById.get(id)?.f.path).filter(Boolean),
  });
  const openDeleteImages = (ids, bytes, paths, done) => setDel({ ids, bytes, paths, similar: true, done });

  if (fatal) return <div className="fatal">{fatal}</div>;
  if (!cfg) return null;

  const focusGroup = focus !== null ? groupById.get(focus) : null;
  const nav = NAV.find(n => n.id === view);
  const counts = {
    dedup: groups.length, folders: res?.folders.length ?? 0,
    watch: watch.events.filter(e => e.id > watchSeen).length,
  };
  const selectionBar = res && !running && groups.length > 0 && (view === 'dedup' || view === 'folders');

  return (
    <TreeCtx.Provider value={{ selected, focus, act, expand, arcSep, arcOk }}>
      <div className="shell">
        <Sidebar cfg={cfg} view={view} setView={setView} counts={counts} running={running}
          onScan={startScan} onCancel={cancelScan} onElevate={elevate} />

        <div className="workspace">
          <header className="topbar">
            <div className="search">
              <Search size={14} />
              <input type="search" id="filter" placeholder="Filter duplicates by name or path…" value={filter}
                onChange={e => { setFilter(e.target.value); setView('dedup'); }} disabled={!res} aria-label="Filter the results" />
            </div>
            <div className="top-pills">
              {res && <span className="pill mono"><b>{fmtNum(res.files_seen)}</b> files examined</span>}
              {res?.cache_hits > 0 && <span className="pill mono" title="Hashes reused from earlier scans (files not changed)"><b>{fmtNum(res.cache_hits)}</b> from cache</span>}
              <span className="pill"><i className={'ping' + (running ? '' : ' idle')} />
                <span>Engine: <span className="mono emerald">BLAKE2b</span> {running ? '(scanning…)' : '(64 KB quick + full)'}</span></span>
              {cfg.admin && <span className="pill amber">Administrator</span>}
            </div>
          </header>

          <main className="canvas">
            <div className="page-head">
              <div className="crumbs"><span>{nav.crumb}</span><span>/</span><span>{nav.title.toUpperCase()}</span></div>
              <div className="title-row">
                <h1>{nav.title}</h1>
                {view === 'dedup' && res && !running && <button className="btn ghost sm" onClick={() => setShowScan(v => !v)}>{showScan ? 'Hide settings' : 'Scan settings'}</button>}
              </div>
              <p>{INTRO[view]}</p>
            </div>

            {stale && <div className="banner amber" role="status">Files were extracted or moved: the results may no longer match the disk.
              <button className="btn ghost sm" onClick={startScan} disabled={running}>Scan again</button></div>}
            {res && !stale && res.finished && Date.now() / 1000 - res.finished > 86400 && view === 'dedup' &&
              <div className="banner">These results come from a scan of {new Date(res.finished * 1000).toLocaleString('en-GB')}: scan again if files changed since.</div>}

            {view === 'dedup' && <>
              {(showScan || !res || running) && <ScanPanel cfg={cfg} value={form} onChange={setForm} running={running} onScan={startScan} onCancel={cancelScan} />}
              {running && <Progress st={st} />}

              {res && !running && <>
                <Summary meta={res} groups={groups} selBytes={selBytes} arcOk={arcOk} />

                <div className="toolbar">
                  <div className="tool-group">
                    <div className="seg-toggle">
                      <button onClick={() => setExpand(e => ({ mode: 'expand', v: e.v + 1, budget: { n: 0 } }))}>Expand all</button>
                      <button onClick={() => setExpand(e => ({ mode: 'collapse', v: e.v + 1, budget: { n: 0 } }))}>Collapse</button>
                    </div>
                    <span className="vsep" />
                    <label className="small muted" htmlFor="strategy">Strategy:</label>
                    <select id="strategy" value={strategy} onChange={e => setStrategy(e.target.value)} title="Automatic selection across all groups">
                      <option value="">Choose a rule…</option>
                      {Object.entries(STRATEGIES).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
                    </select>
                    <button className={'btn ghost sm' + (showRules ? ' on' : '')} onClick={() => setShowRules(v => !v)} aria-expanded={showRules}>
                      Preferred folders{preferList.length ? ` (${preferList.length})` : ''}</button>
                    <button className="btn primary sm" onClick={runStrategy}>Apply</button>
                    {preview && preview.add + preview.rem > 0 && <span className="small muted" title="Effect of Apply on the current selection">
                      → <span className="crimson">+{fmtNum(preview.add)}</span> / <span className="emerald">−{fmtNum(preview.rem)}</span> files ({preview.addB >= preview.remB ? '+' : '−'}{fmtSize(Math.abs(preview.addB - preview.remB))})</span>}
                  </div>
                  <div className="tool-group">
                    <label className="check small" title="A copy inside an archive that has not changed since the scan is enough to keep: the disk copies can all go">
                      <input type="checkbox" checked={arcOk} onChange={e => setArcKeep(e.target.checked)} />Copies in archives count as kept</label>
                    <button className="btn ghost sm" onClick={exportCsv}>Export CSV</button>
                  </div>
                </div>
                {showRules && <div className="panel rules">
                  <label className="label-caps" htmlFor="prefer">Preferred folders <span className="hint">one per line, most important first</span></label>
                  <textarea id="prefer" rows={3} spellCheck={false} value={prefer} onChange={e => savePrefer(e.target.value)}
                    placeholder={'D:\\Archive\nC:\\Users\\Mario\\Pictures'} />
                  <p className="hint">With any strategy, each group keeps the copy in the first matching folder; the strategy only breaks ties.
                    Example: keep everything in D:\Archive, delete from Desktop and Downloads.</p>
                </div>}

                <div className="legend">
                  <span><i className="sw emerald" />Kept</span>
                  <span><i className="sw crimson" />To delete</span>
                  <span><i className="sw violet" />In archive (read-only)</span>
                </div>
                <div className="split">
                  <Tree root={root} empty={groups.length === 0} />
                  <Inspector g={focusGroup} toast={toast} />
                </div>
              </>}
            </>}

            {view === 'folders' && <Folders res={res} arcSep={arcSep} act={act} toast={toast} />}
            {view === 'inventory' && <Inventory res={res} toast={toast} />}
            {view === 'images' && <Images cfg={cfg} res={res} toast={toast} onDelete={openDeleteImages} />}
            {view === 'catalog' && <Catalog cfg={cfg} toast={toast} />}
            {view === 'quarantine' && <Quarantine cfg={cfg} toast={toast} />}
            {view === 'watch' && <Watcher watch={watch} onChange={setWatch} toast={toast} />}
          </main>

          {selectionBar && (
            <footer className="actionbar">
              <div className="actionbar-left">
                <span className="actionbar-ico"><Trash size={16} /></span>
                <span className="actionbar-count">{selected.size === 1 ? '1 file selected' : `${fmtNum(selected.size)} files selected`}</span>
                {selected.size > 0 && <span className="free-badge">{fmtSize(selBytes)} to free</span>}
              </div>
              <div className={'actionbar-rule' + (fullGroups ? ' amber' : '')}>
                {fullGroups ? <Alert size={16} /> : <Check size={16} />}
                <span>{fullGroups
                  ? `In ${nGroups(fullGroups)} you selected every copy on disk: keep at least one${arcOk ? ' (or a copy in an archive)' : ''}.`
                  : arcOk ? 'Active rule: every group keeps a copy on disk or in an unchanged archive.'
                    : 'Active rule: at least one copy of every group always stays on disk.'}</span>
              </div>
              <div className="actionbar-right">
                <button className="btn text" disabled={!selected.size} onClick={() => setSelected(new Set())}>Deselect all</button>
                <button className="btn danger" disabled={!selected.size || fullGroups > 0} onClick={openDelete}>
                  <Trash size={16} />Delete {selected.size === 1 ? '1 selected file' : `${fmtNum(selected.size)} selected files`}…</button>
              </div>
            </footer>
          )}
        </div>
      </div>

      {del && <DeleteDialog cfg={cfg} ids={del.ids} bytes={del.bytes} paths={del.paths} similar={del.similar} arcKeep={arcOk && !del.similar}
        onClose={() => setDel(null)} onDeleted={del.done} toast={toast} onElevate={elevate} />}
      {extractArc && <ExtractDialog cfg={cfg} archive={extractArc} onClose={() => setExtractArc(null)} onChanged={() => setStale(true)} />}
      <div className={'toast' + (toastMsg ? ' show' : '')} role="status">{toastMsg}</div>
    </TreeCtx.Provider>
  );
}
