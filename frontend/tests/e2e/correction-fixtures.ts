/**
 * Shared fixture helpers for correction workbench E2E specs.
 *
 * Strategy (B+C hybrid):
 *   - Uses the backend test-only endpoint POST /api/v1/correction/sessions/_test/seed
 *     (enabled when ENV != "production") to create a CorrectionSession with
 *     pre-populated segments via the existing API — no audio upload needed.
 *   - All specs call seedCorrectionSession() in their setup block.
 *   - E2E_API_TOKEN must be set (defaults to the dev bootstrap key for local runs).
 *
 * Preconditions for actual execution:
 *   - Backend running with DEPLOYMENT_PROFILE=vendor (correction router enabled)
 *   - ENV=development or ENV=staging (not production)
 *   - Frontend dev server running on FRONTEND_BASE_URL (default http://localhost:3000)
 */

import { type Page } from '@playwright/test';

export const TOKEN = process.env.E2E_API_TOKEN ?? 'please-change-me-to-strong-token';
export const BACKEND_URL = process.env.BACKEND_BASE_URL ?? 'http://localhost:8000';

/**
 * Inject the bearer token into localStorage so the Next.js app authenticates.
 * Must be called in test.beforeEach via context.addInitScript.
 */
export async function injectToken(page: Page, token = TOKEN): Promise<void> {
  await page.addInitScript((t: string) => {
    localStorage.setItem('qwen-asr-token', t);
  }, token);
}

/**
 * Call the test-only seed endpoint and return the created session_id.
 * @param page  Playwright Page (for request context access)
 * @param segmentCount  Number of segments to create (default 3)
 */
export async function seedCorrectionSession(
  page: Page,
  segmentCount = 3,
): Promise<number> {
  const resp = await page.request.post(
    `${BACKEND_URL}/api/v1/correction/sessions/_test/seed?segment_count=${segmentCount}`,
    {
      headers: { Authorization: `Bearer ${TOKEN}` },
    },
  );
  if (!resp.ok()) {
    const body = await resp.text();
    throw new Error(
      `seedCorrectionSession failed: HTTP ${resp.status()} — ${body}`,
    );
  }
  const envelope = await resp.json();
  return envelope.data.session_id as number;
}

/**
 * Navigate to the correction workbench for the given sessionId and wait
 * until the 3-column layout is visible.
 */
export async function gotoSession(page: Page, sessionId: number): Promise<void> {
  await page.goto(`/correction/${sessionId}`);
  // Wait for all three panels to be present in the DOM
  await page.getByLabel('音訊區').waitFor({ state: 'visible', timeout: 15_000 });
  await page.getByLabel('段落清單').waitFor({ state: 'visible', timeout: 5_000 });
  await page.getByLabel('文字編輯區').waitFor({ state: 'visible', timeout: 5_000 });
}
