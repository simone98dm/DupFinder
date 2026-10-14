import { useEffect, useState } from 'react';
import { apiBlob } from '../api.js';

const IMG = /\.(jpe?g|png|webp|bmp|gif|tiff?)$/i;
const TXT = /\.(txt|md|csv|log|json|xml|ini|cfg|py|js|html|css)$/i;
export const previewable = path => IMG.test(path) || TXT.test(path);

/* Thumbnail of an image or the first lines of a text file (set: 'dup' scan results, 'sim' similar images). */
export default function Preview({ id, path, set = 'dup', className = '' }) {
  const [p, setP] = useState(null);
  const [err, setErr] = useState('');
  useEffect(() => {
    let url, live = true;
    setP(null);
    setErr('');
    if (!previewable(path)) return;
    apiBlob(`/api/preview?set=${set}&id=${id}`).then(r => {
      url = r.url;
      if (live) setP(r);
    }).catch(e => live && setErr(e.message));
    return () => { live = false; if (url?.startsWith('blob:')) URL.revokeObjectURL(url); };
  }, [id, path, set]);
  if (!previewable(path)) return null;
  if (err) return <div className={'preview muted small ' + className}>{err}</div>;
  if (!p) return <div className={'preview loading ' + className} aria-busy="true" />;
  if (p.text !== undefined) return <pre className={'preview text ' + className} aria-hidden="true">{p.text}</pre>;
  return <div className={'preview ' + className}><img src={p.url} alt={path.split(/[\\/]/).pop()} loading="lazy" /></div>;
}
