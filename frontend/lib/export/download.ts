// Defensive：a.download 雖被瀏覽器 sanitize，仍主動剝離路徑分隔字元 + 控制字元，
// 避免 stored.data.transcription_id 為 corrupt 字串時觸發歧義路徑。
export function sanitizeFilename(name: string): string {
  return name
    .replace(/[\\/:*?"<>| -]/g, '_')
    .replace(/\.{2,}/g, '_')
    .slice(0, 200);
}

export function triggerDownload(filename: string, content: string, mimeType: string): void {
  const safe = sanitizeFilename(filename);
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = safe;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
