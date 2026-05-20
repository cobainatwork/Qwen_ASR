/**
 * UUID v4 helper with fallback for non-secure HTTP origins.
 *
 * `crypto.randomUUID()` 只在 secure context（HTTPS 或 http://localhost / 127.0.0.1）
 * 可用。本專案 dev 部署常透過 LAN IP（如 http://10.2.66.102:3000）連線，使用者
 * 瀏覽器拿到的 window.crypto.randomUUID 是 undefined。本檔提供降級：
 *   1. 優先用 crypto.randomUUID（secure context / Node 19+）
 *   2. 退而求其次：crypto.getRandomValues 取 16 bytes 自組 RFC 4122 v4 UUID
 *   3. 最終降級：Math.random（功能正確；用於 Idempotency-Key 用途強度足夠）
 */

export function randomUuid(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  const bytes = new Uint8Array(16);
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256);
  }

  // RFC 4122 §4.4：version 4 + variant bits
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  const hex: string[] = [];
  for (let i = 0; i < 16; i++) hex.push(bytes[i].toString(16).padStart(2, '0'));

  return (
    hex.slice(0, 4).join('') +
    '-' +
    hex.slice(4, 6).join('') +
    '-' +
    hex.slice(6, 8).join('') +
    '-' +
    hex.slice(8, 10).join('') +
    '-' +
    hex.slice(10, 16).join('')
  );
}
