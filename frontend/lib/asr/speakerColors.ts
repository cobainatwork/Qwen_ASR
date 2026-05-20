// FNV-1a 32-bit hash: pure function, stable, no dependencies
function hash(label: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < label.length; i++) {
    h ^= label.charCodeAt(i);
    h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
  }
  return h;
}

const GOLDEN_ANGLE = 137.508;

function hue(label: string): number {
  const base = hash(label) % 360;
  // Apply golden angle to spread consecutive SPEAKER_00 / 01 / 02 ...
  return (base + GOLDEN_ANGLE) % 360;
}

export function speakerColor(label: string): string {
  const h = hue(label);
  return `hsl(${h.toFixed(1)}, 65%, 45%)`;
}

export function speakerBgColor(label: string): string {
  const h = hue(label);
  return `hsla(${h.toFixed(1)}, 65%, 60%, 0.25)`;
}
