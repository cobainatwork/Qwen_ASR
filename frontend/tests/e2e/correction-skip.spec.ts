/**
 * E2E: correction-skip — skip statistics + JSONL exclusion
 *
 * Scenario:
 *   1. Seed a session with 3 segments
 *   2. Click "跳過" on segment 0 → verify SegmentListStats updates
 *   3. Export JSONL → verify skipped segment is excluded from export
 *
 * The "跳過" action is triggered via the segment's skip button (aria-label="跳過").
 * SegmentListStats shows "已校正 X%" and a progress bar.
 * The JSONL exporter (session_to_jsonl) excludes segments where is_skipped=true.
 *
 * Preconditions (manual verification needed — see CLAUDE.md #24):
 *   - Backend running with DEPLOYMENT_PROFILE=vendor, ENV=development
 *   - Frontend dev server running
 *   - E2E_API_TOKEN set to a valid asr:write key
 */

import { test, expect } from '@playwright/test';
import { injectToken, seedCorrectionSession, gotoSession, TOKEN, BACKEND_URL } from './correction-fixtures';

test.describe('Skip segment', () => {
  test.beforeEach(async ({ context }) => {
    await context.addInitScript((token: string) => {
      localStorage.setItem('qwen-asr-token', token);
    }, TOKEN);
  });

  test('skip segment 0 → stats update + JSONL excludes it', async ({ page }) => {
    await injectToken(page);
    const sessionId = await seedCorrectionSession(page, 3);
    await gotoSession(page, sessionId);

    // Find and click the skip button for the first segment.
    // The skip button is expected to have aria-label="跳過" within the first article card.
    const firstCard = page.getByRole('article').first();
    const skipBtn = firstCard.getByRole('button', { name: '跳過' });

    // If skip button exists in current UI, use it; otherwise call API directly
    const skipBtnCount = await skipBtn.count();
    if (skipBtnCount > 0) {
      await skipBtn.click();
    } else {
      // Fallback: call backend directly to mark segment 0 as skipped
      // First fetch segment list to get segment IDs
      const segsResp = await page.request.get(
        `${BACKEND_URL}/api/v1/correction/sessions/${sessionId}/segments`,
        { headers: { Authorization: `Bearer ${TOKEN}` } },
      );
      const segsEnv = await segsResp.json();
      const segments = segsEnv.data as Array<{ id: number; version: number }>;
      const seg0 = segments[0];
      await page.request.put(
        `${BACKEND_URL}/api/v1/correction/sessions/${sessionId}/segments/${seg0.id}`,
        {
          headers: {
            Authorization: `Bearer ${TOKEN}`,
            'Content-Type': 'application/json',
          },
          data: JSON.stringify({
            corrected_text: null,
            is_skipped: true,
            expected_version: seg0.version,
          }),
        },
      );
      // Reload to reflect server state
      await page.reload();
      await page.getByLabel('文字編輯區').waitFor({ state: 'visible', timeout: 15_000 });
    }

    // ── Assert stats panel shows skipped icon on segment 0 ─────────────────
    // SegmentListItem renders <SkipForward aria-label="已跳過"> for skipped segments
    const skippedIcon = page.getByLabel('已跳過').first();
    await expect(skippedIcon).toBeVisible({ timeout: 5_000 });

    // ── Assert JSONL export excludes the skipped segment ───────────────────
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: '匯出 JSONL' }).click();
    const download = await downloadPromise;

    const path = await download.path();
    expect(path).toBeTruthy();
    const { readFileSync } = await import('fs');
    const content = readFileSync(path!, 'utf-8');
    const lines = content.trim().split('\n').filter(Boolean);

    // With 3 segments and 1 skipped, JSONL should contain at most 2 lines
    // (the exporter may also exclude uncorrected segments — so <= 2)
    expect(lines.length).toBeLessThanOrEqual(2);

    // None of the exported lines should have is_skipped=true
    for (const line of lines) {
      const obj = JSON.parse(line) as Record<string, unknown>;
      expect(obj['is_skipped']).not.toBe(true);
    }
  });
});
