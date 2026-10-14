import { fmtNum, fmtSize } from '../format.js';

export default function Progress({ st }) {
  let phase = 'Starting…', count = '', pct = null;
  if (st.phase === 'walk') { phase = 'Finding files'; count = fmtNum(st.files_seen) + ' files examined'; }
  else if (st.phase === 'archives') { phase = 'Reading archives'; count = `${fmtNum(st.done)} of ${fmtNum(st.total)} archives`; pct = st.total ? st.done / st.total : 1; }
  else if (st.phase === 'partial') { phase = 'Quick comparison of candidates'; count = `${fmtNum(st.done)} of ${fmtNum(st.total)}`; pct = st.total ? st.done / st.total : 1; }
  else if (st.phase === 'full') { phase = 'Full content check'; count = `${fmtSize(Math.min(st.bytes_done, st.bytes_total))} of ${fmtSize(st.bytes_total)}`; pct = st.bytes_total ? st.bytes_done / st.bytes_total : 1; }

  return (
    <section className="panel progress" aria-live="polite">
      <div className="progress-head">
        <span className="dot pulse" />
        <strong>{phase}</strong>
        <span className="mono muted">{count}{st.elapsed ? ` · ${Math.round(st.elapsed)} s` : ''}</span>
        {pct !== null && <span className="grow mono right cyan">{Math.min(100, pct * 100).toFixed(0)}%</span>}
      </div>
      <div className={'track' + (pct === null ? ' indet' : '')}>
        <div className="fill" style={pct === null ? undefined : { width: Math.min(100, pct * 100).toFixed(1) + '%' }} />
      </div>
      <div className="mono muted ellip small">{st.current || '\u00a0'}</div>
    </section>
  );
}
