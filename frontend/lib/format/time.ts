const sanitize = (v: number) => (Number.isFinite(v) && v > 0 ? v : 0);

export function formatTimestamp(seconds: number): string {
  const s = sanitize(seconds);
  const totalMin = Math.floor(s / 60);
  const rem = s - totalMin * 60;
  const secInt = Math.floor(rem);
  const tenth = Math.round((rem - secInt) * 10);
  return `${String(totalMin).padStart(2, '0')}:${String(secInt).padStart(2, '0')}.${tenth}`;
}

export function formatDuration(seconds: number): string {
  const s = sanitize(Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) {
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  }
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}

function hmsms(seconds: number, msSep: ',' | '.'): string {
  const s = sanitize(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  const ms = Math.round((s - Math.floor(s)) * 1000);
  return (
    `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:` +
    `${String(sec).padStart(2, '0')}${msSep}${String(ms).padStart(3, '0')}`
  );
}

export function formatSrtTimestamp(seconds: number): string {
  return hmsms(seconds, ',');
}

export function formatVttTimestamp(seconds: number): string {
  return hmsms(seconds, '.');
}
