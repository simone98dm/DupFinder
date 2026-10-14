import { useCallback, useEffect, useState } from 'react';
import { api, IS_APP, pickFolder } from '../api.js';
import { fmtNum, fmtSize } from '../format.js';
import { Folder, Stop } from './Icons.jsx';

const PHASES = {
  walk: 'Listing files', hash: 'Computing hashes', write: 'Writing the archive', verify: 'Reading the archive back',
  extract: 'Extracting', archive: 'Removing the archive', compare: 'Comparing images',
};

/* State of a background job (archive, verify, restore, extract, similar), polled while it runs. */
export function useJob(kind, onFinish) {
  const [st, setSt] = useState({ state: 'idle' });
  const running = st.state === 'running';
  useEffect(() => { api('/api/job?kind=' + kind).then(setSt).catch(() => {}); }, [kind]);
  useEffect(() => {
    if (!running) return;
    const t = setTimeout(() => api('/api/job?kind=' + kind).then(s => {
      setSt(s);
      if (s.state !== 'running') onFinish?.(s);
    }).catch(() => setSt(s => ({ ...s }))), 400);
    return () => clearTimeout(t);
  }, [st, running, kind]);   // eslint-disable-line react-hooks/exhaustive-deps
  const start = useCallback(async body => setSt(await api('/api/job/start', { kind, ...body })), [kind]);
  const cancel = useCallback(() => api('/api/job/cancel', { kind }), [kind]);
  const reset = useCallback(() => setSt({ state: 'idle' }), []);
  return { st, running, start, cancel, reset };
}

export function JobProgress({ st, onCancel }) {
  if (st.state !== 'running') return null;
  const pct = st.bytes_total ? st.bytes_done / st.bytes_total : st.total ? st.done / st.total : null;
  return (
    <div className="panel progress" aria-live="polite">
      <div className="progress-head">
        <span className="dot pulse" />
        <strong>{PHASES[st.phase] || 'Working…'}</strong>
        <span className="mono muted">
          {st.total ? `${fmtNum(st.done)} of ${fmtNum(st.total)}` : ''}
          {st.bytes_total ? ` · ${fmtSize(Math.min(st.bytes_done, st.bytes_total))} of ${fmtSize(st.bytes_total)}` : ''}
          {st.elapsed ? ` · ${Math.round(st.elapsed)} s` : ''}
        </span>
        {pct !== null && <span className="grow mono right cyan">{Math.min(100, pct * 100).toFixed(0)}%</span>}
        {onCancel && <button className="btn ghost sm" onClick={onCancel}><Stop size={12} />Cancel</button>}
      </div>
      <div className={'track' + (pct === null ? ' indet' : '')}>
        <div className="fill" style={pct === null ? undefined : { width: Math.min(100, pct * 100).toFixed(1) + '%' }} />
      </div>
      <div className="mono muted ellip small">{st.current || ' '}</div>
    </div>
  );
}

/* The outcome of a finished job that failed or was cancelled. */
export function JobError({ st }) {
  if (st.state === 'error') return <div className="banner crimson" role="alert">{st.message}</div>;
  if (st.state === 'cancelled') return <div className="banner">Cancelled.</div>;
  return null;
}

/* A folder path: typed, or chosen with the native dialog in the desktop app. */
export function FolderField({ id, value, onChange, placeholder }) {
  async function browse() {
    const p = await pickFolder(value);
    if (p) onChange(p);
  }
  return (
    <div className="folder-field">
      <input id={id} type="text" className="text mono" spellCheck={false} value={value} placeholder={placeholder}
        onChange={e => onChange(e.target.value)} />
      {IS_APP && <button type="button" className="btn ghost sm" onClick={browse}><Folder size={12} />Browse…</button>}
    </div>
  );
}

/* A list of folders, one per line, with "Add folder…" in the desktop app. */
export function FoldersField({ id, value, onChange, placeholder, rows = 3 }) {
  async function add() {
    const p = await pickFolder();
    if (p) onChange((value.trim() ? value.trim() + '\n' : '') + p);
  }
  return (
    <>
      <textarea id={id} rows={rows} spellCheck={false} value={value} placeholder={placeholder} onChange={e => onChange(e.target.value)} />
      {IS_APP && <div><button type="button" className="btn ghost sm" onClick={add}><Folder size={12} />Add folder…</button></div>}
    </>
  );
}

export const lines = s => s.split('\n').map(x => x.trim()).filter(Boolean);
