/**
 * E2E: correction-idb-resume — IndexedDB pending-draft resume + retry
 *
 * Scenario:
 *   1. Edit a segment textarea
 *   2. Immediately reload (before autosave debounce fires → draft stays in IDB as "pending")
 *   3. Revisit page → app reads IDB draft, re-hydrates textarea, retries save
 *   4. Wait for autosave → textarea still has the edited value + "已儲存" shown
 *
 * IDB persistence relies on useDebouncedSave writing syncStatus='pending' to idb-keyval
 * before the network call. After reload, useDebouncedSave picks up pending drafts and
 * retries automatically.
 *
 * Preconditions (manual verification needed — see CLAUDE.md #24):
 *   - Backend running with DEPLOYMENT_PROFILE=vendor, ENV=development
 *   - Frontend dev server running
 *   - E2E_API_TOKEN set to a valid asr:write key
 */

import { test, expect } from '@playwright/test';
import { injectToken, seedCorrectionSession, gotoSession, TOKEN } from './correction-fixtures';

test.describe('IDB draft resume', () => {
  test.beforeEach(async ({ context }) => {
    await context.addInitScript((token: string) => {
      localStorage.setItem('qwen-asr-token', token);
    }, TOKEN);
  });

  test('draft survives hard reload and auto-retries save', async ({ page }) => {
    await injectToken(page);
    const sessionId = await seedCorrectionSession(page, 2);
    await gotoSession(page, sessionId);

    // Edit the first textarea
    const firstTextarea = page.getByRole('textbox').first();
    await firstTextarea.click();
    const draftText = 'IDB 草稿文字';
    await firstTextarea.fill(draftText);

    // Reload immediately — before the 2 s debounce fires.
    // The IDB write happens synchronously inside setDraft → useDebouncedSave
    // saves to IDB before the network request.
    await page.reload();

    // After reload, app must re-hydrate textarea from IDB
    await page.getByLabel('文字編輯區').waitFor({ state: 'visible', timeout: 15_000 });
    const resumedTextarea = page.getByRole('textbox').first();

    // The textarea should show the draft value (IDB resume)
    await expect(resumedTextarea).toHaveValue(draftText, { timeout: 8_000 });

    // Auto-retry saves to backend → eventually shows "已儲存"
    await expect(page.getByText('已儲存 ✓').first()).toBeVisible({ timeout: 8_000 });
  });
});
