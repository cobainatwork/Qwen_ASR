/**
 * E2E: correction-shortcuts — 5 keyboard shortcuts
 *
 * Shortcuts under test (from useCorrectionShortcuts.ts):
 *   1. Space        → playToggle (audio play/pause)
 *   2. Ctrl+S       → force save focused segment
 *   3. Ctrl+Enter   → save + advance to next segment
 *   4. Ctrl+F       → focus search input
 *   5. Escape       → blur textarea (when in text field) or exit focusMode
 *
 * Observable effects without a real audio backend:
 *   - Space: triggers play; no crash (audio panel handles gracefully)
 *   - Ctrl+S: marks focused segment as saving → "儲存中…" or "已儲存"
 *   - Ctrl+Enter: focused segment advances (aria-current moves to next item)
 *   - Ctrl+F: search input receives focus
 *   - Escape: blurs textarea (document.activeElement changes)
 *
 * Preconditions (manual verification needed — see CLAUDE.md #24):
 *   - Backend running with DEPLOYMENT_PROFILE=vendor, ENV=development
 *   - Frontend dev server running
 *   - E2E_API_TOKEN set to a valid asr:write key
 */

import { test, expect } from '@playwright/test';
import { injectToken, seedCorrectionSession, gotoSession, TOKEN } from './correction-fixtures';

test.describe('Keyboard shortcuts', () => {
  test.beforeEach(async ({ context }) => {
    await context.addInitScript((token: string) => {
      localStorage.setItem('qwen-asr-token', token);
    }, TOKEN);
  });

  test('Ctrl+F focuses search input', async ({ page }) => {
    await injectToken(page);
    const sessionId = await seedCorrectionSession(page, 2);
    await gotoSession(page, sessionId);

    // Focus body first (not a text field)
    await page.locator('body').click();
    await page.keyboard.press('Control+f');

    // The search input should now be focused
    const searchInput = page.getByPlaceholder(/搜尋|search/i);
    await expect(searchInput).toBeFocused({ timeout: 3_000 });
  });

  test('Escape blurs textarea', async ({ page }) => {
    await injectToken(page);
    const sessionId = await seedCorrectionSession(page, 2);
    await gotoSession(page, sessionId);

    const firstTextarea = page.getByRole('textbox').first();
    await firstTextarea.click();
    await expect(firstTextarea).toBeFocused();

    await page.keyboard.press('Escape');

    // After Escape the textarea should no longer be focused
    await expect(firstTextarea).not.toBeFocused({ timeout: 2_000 });
  });

  test('Ctrl+S triggers save on focused segment', async ({ page }) => {
    await injectToken(page);
    const sessionId = await seedCorrectionSession(page, 2);
    await gotoSession(page, sessionId);

    // Type into first textarea to create a draft
    const firstTextarea = page.getByRole('textbox').first();
    await firstTextarea.click();
    await firstTextarea.fill('Ctrl+S 測試文字');

    // Press Ctrl+S — expect save indicator to appear
    await page.keyboard.press('Control+s');

    // Should show "儲存中…" or "已儲存 ✓" within a few seconds
    const saveIndicator = page.getByText(/儲存中|已儲存/).first();
    await expect(saveIndicator).toBeVisible({ timeout: 5_000 });
  });

  test('Ctrl+Enter advances focus to next segment', async ({ page }) => {
    await injectToken(page);
    const sessionId = await seedCorrectionSession(page, 3);
    await gotoSession(page, sessionId);

    // Click first segment list item to focus segment 0
    const listItems = page.getByRole('listitem');
    await listItems.first().click();

    // Confirm segment 0 is aria-current
    await expect(listItems.first()).toHaveAttribute('aria-current', 'true', { timeout: 3_000 });

    // Focus the first textarea and press Ctrl+Enter
    const firstTextarea = page.getByRole('textbox').first();
    await firstTextarea.click();
    await page.keyboard.press('Control+Enter');

    // After Ctrl+Enter, segment 1 list item should become aria-current
    await expect(listItems.nth(1)).toHaveAttribute('aria-current', 'true', { timeout: 3_000 });
  });

  test('Space triggers audio playToggle without crash', async ({ page }) => {
    await injectToken(page);
    const sessionId = await seedCorrectionSession(page, 2);
    await gotoSession(page, sessionId);

    // Focus body so Space is not captured by a text field
    await page.locator('body').click();

    // Pressing Space should not throw; page still shows the layout
    await page.keyboard.press('Space');
    await expect(page.getByLabel('音訊區')).toBeVisible();
  });
});
