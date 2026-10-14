import { useEffect, useRef } from 'react';
import { version } from '../../package.json';    // kept in step with pyproject.toml by release-please
import { Open, Shield } from './Icons.jsx';

const REPO = 'https://github.com/simone98dm/DupFinder';

/* Program name, version, author and links. */
export default function AboutDialog({ cfg, onClose }) {
  const ref = useRef(null);
  const close = useRef(null);
  useEffect(() => { ref.current.showModal(); close.current.focus(); }, []);   // after showModal: it moves focus itself
  return (
    <dialog ref={ref} className="dialog about" onClose={onClose} aria-labelledby="about-title">
      <div className="about-head">
        <span className="brand-logo"><Shield size={20} /></span>
        <div>
          <h2 id="about-title">DupFinder</h2>
          <span className="mono muted">Version {version}</span>
        </div>
      </div>
      <p>Finds duplicate files by content, also inside ZIP, 7z and RAR archives, and keeps unique copies in local archives.</p>
      <dl className="kv-grid">
        <dt>Author</dt><dd><a href="https://github.com/simone98dm" target="_blank" rel="noreferrer">simone98dm</a></dd>
        <dt>Source code</dt><dd><a href={REPO} target="_blank" rel="noreferrer">github.com/simone98dm/DupFinder<Open size={12} /></a></dd>
        <dt>Report a problem</dt><dd><a href={REPO + '/issues'} target="_blank" rel="noreferrer">GitHub issues<Open size={12} /></a></dd>
        <dt>Release notes</dt><dd><a href={REPO + '/releases'} target="_blank" rel="noreferrer">GitHub releases<Open size={12} /></a></dd>
        <dt>License</dt><dd>MIT</dd>
        <dt>Running as</dt><dd>{cfg.app ? 'Desktop app' : 'Browser'} on {{ windows: 'Windows', mac: 'macOS', linux: 'Linux' }[cfg.platform] ?? cfg.platform}</dd>
      </dl>
      <div className="dialog-btns"><button ref={close} className="btn primary" onClick={() => ref.current.close()}>Close</button></div>
    </dialog>
  );
}
