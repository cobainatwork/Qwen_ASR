import fastDiff from 'fast-diff';

export type DiffOp = { type: 'equal' | 'delete' | 'insert'; text: string };

/** 短段使用字元級 diff；長段使用詞級 diff 以降低 ops 數量。 */
const CHAR_LEVEL_THRESHOLD = 200;

/** 詞分隔符：空白 + 常見中英文標點 */
const SPLITTER = /(\s+|[，。！？；：、,.!?;:])/g;

/** 詞級 diff 使用 NUL 作為 token 分隔哨兵字元（不出現在正常文字中）。 */
const SEP = '\x00';

function toOpType(op: -1 | 0 | 1): 'equal' | 'delete' | 'insert' {
  if (op === fastDiff.EQUAL) return 'equal';
  if (op === fastDiff.DELETE) return 'delete';
  return 'insert';
}

/**
 * 計算 original → corrected 的 diff 操作序列。
 *
 * - 兩端字串皆 < 200 字元 → 字元級（fast-diff 直接作用於字元串）
 * - 其中一端 ≥ 200 字元 → 詞級（以空白/標點為邊界 split 成 token，
 *   token 間插入 SEP 哨兵再交給 fast-diff）
 */
export function computeDiff(original: string, corrected: string): DiffOp[] {
  if (original === corrected) return [{ type: 'equal', text: original }];

  if (original.length < CHAR_LEVEL_THRESHOLD && corrected.length < CHAR_LEVEL_THRESHOLD) {
    // 字元級
    return fastDiff(original, corrected).map(([op, text]) => ({
      type: toOpType(op),
      text,
    }));
  }

  // 詞級：以 splitter 分割後，用 SEP 串接成字串再 diff，最後去掉哨兵
  const tokenize = (s: string) => s.split(SPLITTER).filter((t) => t.length > 0);
  const aStr = tokenize(original).join(SEP);
  const bStr = tokenize(corrected).join(SEP);

  return fastDiff(aStr, bStr)
    .map(([op, text]) => ({
      type: toOpType(op),
      // 去除哨兵字元，還原為可讀文字
      text: text.split(SEP).join(''),
    }))
    .filter((o) => o.text.length > 0);
}
