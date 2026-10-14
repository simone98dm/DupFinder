export function fmtSize(b) {
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
  return (i ? b.toFixed(b < 10 ? 2 : 1) : b) + ' ' + u[i];
}
export const fmtNum = n => n.toLocaleString('en-GB');
export const nGroups = n => (n === 1 ? '1 group' : `${fmtNum(n)} groups`);
export const fmtDate = t => new Date(t * 1000).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' });
export const plural = (n, one, many = one + 's') => `${fmtNum(n)} ${n === 1 ? one : many}`;
