const sanitize = (v: number) => (Number.isFinite(v) && v > 0 ? v : 0);

export function formatTimestamp(seconds: number): string {
  const s = sanitize(seconds);
  // Round to deci-seconds FIRST then split. Avoids carry bug where
  // 19.99 → secInt=19, tenth=round(9.94)=10 outputting "00:19.10"
  // instead of "00:20.0". Same fix protects minute carry on 59.99 → 01:00.0.
  const totalDeci = Math.round(s * 10);
  const tenth = totalDeci % 10;
  const totalSec = Math.floor(totalDeci / 10);
  const totalMin = Math.floor(totalSec / 60);
  const secInMin = totalSec % 60;
  return `${String(totalMin).padStart(2, '0')}:${String(secInMin).padStart(2, '0')}.${tenth}`;
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
