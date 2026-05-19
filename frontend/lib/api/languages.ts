// qwen-asr 0.0.6 只接受英文官方語言名稱或 null（自動偵測）。
// 此清單為 frontend 預設提供的常用語言；qwen-asr 實際支援更多，可依需求擴充。
export const LANGUAGE_OPTIONS = [
  { value: '', label: '自動偵測' },
  { value: 'Chinese', label: '中文（國語 / 普通話）' },
  { value: 'Cantonese', label: '粵語' },
  { value: 'English', label: 'English' },
  { value: 'Japanese', label: '日本語' },
  { value: 'Korean', label: '한국어' },
] as const;

export type LanguageValue = (typeof LANGUAGE_OPTIONS)[number]['value'];
