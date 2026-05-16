import { CorrectionApi, CorrectionApiError } from '@/lib/api/correction';

// 全域 fetch mock
const mockFetch = jest.fn();
global.fetch = mockFetch;

function makeMockResponse<T>(data: T, success = true, status = 200) {
  return {
    status,
    json: async () => ({
      success,
      data: success ? data : null,
      error: success ? null : { code: 'ERR', message: '失敗' },
    }),
  } as unknown as Response;
}

describe('CorrectionApi.updateSegment', () => {
  let api: CorrectionApi;

  beforeEach(() => {
    mockFetch.mockReset();
    api = new CorrectionApi({ getToken: () => 'test-token' });
  });

  it('PUT body 含 corrected_text 與 expected_version', async () => {
    const mockSegment = {
      segment_id: 7,
      session_id: 1,
      start_sec: 0,
      end_sec: 5,
      speaker_label: null,
      original_text: '原文測試',
      corrected_text: '校正後測試',
      version: 2,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:01:00Z',
    };

    mockFetch.mockResolvedValueOnce(makeMockResponse(mockSegment));

    const result = await api.updateSegment(7, {
      corrected_text: '校正後測試',
      expected_version: 1,
    });

    // 驗證 PUT endpoint
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/correction/segments/7',
      expect.objectContaining({
        method: 'PUT',
      }),
    );

    // 驗證 body 含兩個欄位
    const callArgs = mockFetch.mock.calls[0][1] as RequestInit;
    const body = JSON.parse(callArgs.body as string);
    expect(body).toEqual({
      corrected_text: '校正後測試',
      expected_version: 1,
    });

    // 驗證回傳值
    expect(result.version).toBe(2);
    expect(result.corrected_text).toBe('校正後測試');
  });

  it('Bearer token 帶入 Authorization header', async () => {
    const mockSegment = {
      segment_id: 7,
      session_id: 1,
      start_sec: 0,
      end_sec: 5,
      speaker_label: null,
      original_text: '原文',
      corrected_text: '校正',
      version: 1,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    mockFetch.mockResolvedValueOnce(makeMockResponse(mockSegment));

    await api.updateSegment(7, { corrected_text: '校正', expected_version: 0 });

    const callArgs = mockFetch.mock.calls[0][1] as RequestInit;
    const headers = callArgs.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer test-token');
  });

  it('伺服器回傳 success=false 時拋出 CorrectionApiError', async () => {
    mockFetch.mockResolvedValueOnce(
      makeMockResponse(null, false, 409) as unknown as Response,
    );
    // 覆蓋使回傳 success=false 的正確結構
    mockFetch.mockReset();
    mockFetch.mockResolvedValueOnce({
      status: 409,
      json: async () => ({
        success: false,
        data: null,
        error: { code: 'CORRECTION_VERSION_MISMATCH', message: '版本衝突' },
      }),
    } as unknown as Response);

    await expect(
      api.updateSegment(7, { corrected_text: '新文字', expected_version: 0 }),
    ).rejects.toBeInstanceOf(CorrectionApiError);
  });
});
