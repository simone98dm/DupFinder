import { useEffect, useState } from 'react';
import { IS_APP, pickFolder } from '../api.js';
import { Folder, Play, Stop } from './Icons.jsx';

const lines = s => s.split('\n').map(x => x.trim()).filter(Boolean);

/* Scan settings (state held by useScanForm in the parent). */
export default function ScanPanel({ cfg, value, onChange, running, onScan, onCancel }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  const addRoot = r => { const l = lines(value.paths); if (!l.includes(r)) l.push(r); set('paths', l.join('\n')); };

  return (
    <section className="panel scan">
      <div className="scan-grid">
        <div className="field">
          <label className="label-caps" htmlFor="paths">Folders or drives to scan <span className="hint">one per line</span></label>
          <textarea id="paths" rows={4} spellCheck={false} value={value.paths}
            placeholder={'C:\\Users\\Mario\\Documents\nD:\\'} onChange={e => set('paths', e.target.value)} />
          <div className="chips">
            {IS_APP && <button className="chip add" onClick={async () => { const p = await pickFolder(); if (p) addRoot(p); }}>
              <Folder size={12} />Add folder…</button>}
            {cfg?.roots.map(r => (
              <button key={r} className="chip" onClick={() => addRoot(r)}><Folder size={12} />{r}</button>
            ))}
          </div>
        </div>
        <div className="field">
          <label className="label-caps" htmlFor="excludes">Folders to exclude <span className="hint">names or patterns, comma-separated</span></label>
          <textarea id="excludes" rows={4} spellCheck={false} value={value.excludes} onChange={e => set('excludes', e.target.value)} />
          <label className="check"><input type="checkbox" checked={value.skipSystem} onChange={e => set('skipSystem', e.target.checked)} />
            Skip system folders (Windows, Program Files, /usr…)</label>
          <label className="check"><input type="checkbox" checked={value.archives} onChange={e => set('archives', e.target.checked)} />
            Also scan the contents of ZIP, 7z and RAR archives</label>
          {cfg && <div className="hint indent">
            Up to {cfg.max_nest} levels of nested archives. {cfg.sevenzip
              ? '7-Zip found: 7z and RAR included.'
              : '7-Zip not found: only ZIPs will be read. Install 7-Zip from 7-zip.org to include 7z and RAR.'}
          </div>}
        </div>
      </div>
      <div className="scan-foot">
        <label className="inline">Ignore files smaller than
          <input type="number" min="0" step="1" value={value.minKb} onChange={e => set('minKb', e.target.value)} /> KB</label>
        <span className="grow" />
        {running
          ? <button className="btn ghost" onClick={onCancel}><Stop size={14} />Cancel</button>
          : <button className="btn primary" onClick={onScan}><Play size={14} />Start scan</button>}
      </div>
    </section>
  );
}

export function useScanForm(cfg) {
  const [form, setForm] = useState({ paths: '', excludes: '', minKb: '1', skipSystem: true, archives: true });
  useEffect(() => {
    if (cfg) setForm(f => ({ ...f, paths: cfg.prefill.join('\n'), excludes: cfg.excludes.join(', ') }));
  }, [cfg]);
  const body = () => ({
    paths: lines(form.paths),
    min_size: Math.max(1, Math.round(parseFloat(form.minKb || '0') * 1024)),
    excludes: form.excludes.split(/[,\n]/).map(s => s.trim()).filter(Boolean),
    skip_system: form.skipSystem,
    archives: form.archives,
  });
  return [form, setForm, body];
}
