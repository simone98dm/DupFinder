import { Chart, Copy, Database, Eye, FolderFill, Logo, Shield, Trash } from './Icons.jsx';
import { fmtNum } from '../format.js';

export const NAV = [
  { id: 'dedup', label: 'Deduplication', icon: Logo, title: 'Content deduplication', crumb: 'BLAKE2B ENGINE' },
  { id: 'folders', label: 'Similar folders', icon: FolderFill, title: 'Similar folders', crumb: 'BACKUP COPIES' },
  { id: 'images', label: 'Similar images', icon: Copy, title: 'Similar images', crumb: 'PERCEPTUAL HASH' },
  { id: 'inventory', label: 'Inventory', icon: Chart, title: 'Inventory', crumb: 'STATISTICS' },
  { id: 'catalog', label: 'Catalog & archives', icon: Database, title: 'Catalog and incremental archives', crumb: 'SQLITE CATALOG' },
  { id: 'quarantine', label: 'Quarantine', icon: Trash, title: 'Quarantine', crumb: 'RESTORE' },
  { id: 'watch', label: 'Inbox watcher', icon: Eye, title: 'Inbox watcher', crumb: 'WATCHER' },
];

export default function Sidebar({ cfg, view, setView, counts, running, onScan, onCancel, onElevate }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-logo"><Shield size={20} /></span>
        <div>
          <div className="brand-name">DupFinder</div>
          <div className="brand-sub">Cross-platform backup · {cfg?.app ? 'desktop app' : 'browser'}</div>
        </div>
      </div>

      <nav className="nav" aria-label="Modules">
        <div className="label-caps nav-title">Tools</div>
        {NAV.map(({ id, label, icon: Icon }) => (
          <button key={id} className={'nav-item' + (view === id ? ' active' : '')} aria-current={view === id ? 'page' : undefined}
            onClick={() => setView(id)}>
            <Icon size={16} />
            <span className="grow">{label}</span>
            {counts[id] > 0 && <span className={'count' + (id === 'watch' ? ' new' : '')}>{fmtNum(counts[id])}</span>}
          </button>
        ))}
      </nav>

      <div className="sidebar-foot">
        <div className="health">
          <i className={'sw sm ' + (cfg?.sevenzip ? 'emerald' : 'amber')} />
          <span className="grow">{cfg?.sevenzip ? '7-Zip found' : '7-Zip missing'}</span>
          <span className={'mono ' + (cfg?.sevenzip ? 'emerald' : 'amber')}>{cfg ? (cfg.sevenzip ? 'zip·7z·rar' : 'zip only') : '…'}</span>
        </div>
        <div className="health">
          <i className={'sw sm ' + (cfg?.trash ? 'emerald' : 'muted')} />
          <span className="grow">Recycle Bin</span>
          <span className={'mono ' + (cfg?.trash ? 'emerald' : 'muted')}>{cfg ? (cfg.trash ? 'active' : 'quarantine') : '…'}</span>
        </div>
        <div className="health">
          <i className={'sw sm ' + (cfg?.admin ? 'amber' : 'muted')} />
          <span className="grow">Administrator</span>
          {cfg?.can_elevate
            ? <button className="btn link" onClick={onElevate} title="Restart DupFinder with administrator rights (UAC prompt), to delete protected files">Restart as admin</button>
            : <span className={'mono ' + (cfg?.admin ? 'amber' : 'muted')}>{cfg ? (cfg.admin ? 'yes' : 'no') : '…'}</span>}
        </div>
        <button className="side-btn" onClick={running ? onCancel : onScan}>
          <span>{running ? 'Cancel scan' : 'Start scan'}</span>
        </button>
      </div>
    </aside>
  );
}
