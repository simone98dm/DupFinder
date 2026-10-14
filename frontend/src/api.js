// Two transports for the same API:
// - desktop app (pywebview, user agent "DupFinderApp"): window.pywebview.api.call(), no network;
// - browser: HTTP on 127.0.0.1 with the token injected in the page.
export const IS_APP = navigator.userAgent.includes('DupFinderApp');

const bridge = IS_APP ? new Promise(resolve => {
  if (window.pywebview?.api?.call) resolve(window.pywebview.api);
  else window.addEventListener('pywebviewready', () => resolve(window.pywebview.api), { once: true });
}) : null;

let token = document.querySelector('meta[name="dupfinder-token"]')?.content;

// In development the page comes from Vite and has no token: take it from the backend page.
async function getToken() {
  if (token && token !== '__TOKEN__') return token;
  const html = await (await fetch('/__backend__')).text();
  token = html.match(/name="dupfinder-token" content="([^"]+)"/)?.[1];
  return token;
}

async function raw(path, body) {
  if (bridge) {
    const r = await (await bridge).call(body === undefined ? 'GET' : 'POST', path, body ?? null);
    if (r.status >= 400) throw new Error(r.json?.error || 'Error ' + r.status);
    return r;
  }
  const opt = { headers: { 'X-Token': await getToken() } };
  if (body !== undefined) {
    opt.method = 'POST';
    opt.headers['Content-Type'] = 'application/json';
    opt.body = JSON.stringify(body);
  }
  const r = await fetch(path, opt);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || 'HTTP error ' + r.status);
  return r;
}

export async function api(path, body) {
  const r = await raw(path, body);
  return bridge ? r.json : r.json();
}

/* A file preview: { type, url } for images (usable in <img src>), { type, text } for text. */
export async function apiBlob(path) {
  const r = await raw(path);
  if (bridge) {
    if (r.ctype.startsWith('text/')) return { type: r.ctype, text: new TextDecoder().decode(Uint8Array.from(atob(r.b64), c => c.charCodeAt(0))) };
    return { type: r.ctype, url: `data:${r.ctype};base64,${r.b64}` };
  }
  const blob = await r.blob();
  if (blob.type.startsWith('text/')) return { type: blob.type, text: await blob.text() };
  return { type: blob.type, url: URL.createObjectURL(blob) };
}

/* Native folder picker (desktop app only): '' if cancelled, null if not available. */
export async function pickFolder(start = '') {
  return bridge ? (await bridge).pick_folder(start) : null;
}

/* Saves a text file: native "Save as" in the app, a download in the browser. Returns the path or ''. */
export async function saveText(filename, text) {
  if (bridge) return (await bridge).save_text(filename, text);
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(['﻿' + text], { type: 'text/csv;charset=utf-8' }));
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  return filename;
}
