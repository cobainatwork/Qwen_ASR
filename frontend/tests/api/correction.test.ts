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

  it('PUT 路徑含 sessionId 與 segmentId，body 含 corrected_text 與 expected_version', async () => {
    const mockSegment = {
      id: 7,
      session_id: 1,
      segment_index: 2,
      start_sec: 0,
      end_sec: 5,
      original_text: '原文測試',
      corrected_text: '校正後測試',
      version: 2,
      updated_at: '2026-01-01T00:01:00Z',
    };

    mockFetch.mockResolvedValueOnce(makeMockResponse(mockSegment));

    const result = await api.updateSegment(1, 7, {
      corrected_text: '校正後測試',
      expected_version: 1,
    });

    // 驗證 PUT endpoint（巢狀路徑 sessions/{sessionId}/segments/{segmentId}）
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/correction/sessions/1/segments/7',
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

    // 驗證回傳值符合後端 schema（id 而非 segment_id）
    expect(result.id).toBe(7);
    expect(result.version).toBe(2);
    expect(result.corrected_text).toBe('校正後測試');
  });

  it('Bearer token 帶入 Authorization header', async () => {
    const mockSegment = {
      id: 7,
      session_id: 1,
      segment_index: 0,
      start_sec: 0,
      end_sec: 5,
      original_text: '原文',
      corrected_text: '校正',
      version: 1,
      updated_at: '2026-01-01T00:00:00Z',
    };

    mockFetch.mockResolvedValueOnce(makeMockResponse(mockSegment));

    await api.updateSegment(1, 7, { corrected_text: '校正', expected_version: 0 });

    const callArgs = mockFetch.mock.calls[0][1] as RequestInit;
    const headers = callArgs.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer test-token');
  });

  it('伺服器回傳 success=false 時拋出 CorrectionApiError，並帶 code 與 status', async () => {
    mockFetch.mockResolvedValueOnce({
      status: 409,
      json: async () => ({
        success: false,
        data: null,
        error: { code: 'CORRECTION_VERSION_MISMATCH', message: '版本衝突' },
      }),
    } as unknown as Response);

    try {
      await api.updateSegment(1, 7, { corrected_text: '新文字', expected_version: 0 });
      fail('應拋出例外');
    } catch (err) {
      expect(err).toBeInstanceOf(CorrectionApiError);
      expect((err as CorrectionApiError).code).toBe('CORRECTION_VERSION_MISMATCH');
      expect((err as CorrectionApiError).status).toBe(409);
    }
  });
});

describe('CorrectionApi.getSession', () => {
  let api: CorrectionApi;

  beforeEach(() => {
    mockFetch.mockReset();
    api = new CorrectionApi({ baseUrl: '', getToken: () => null });
  });

  it('正確呼叫 GET /sessions/:id 並回傳 session', async () => {
    mockFetch.mockResolvedValueOnce(makeMockResponse({
      id: 1,
      transcription_id: 10,
      name: 'sess',
      status: 'in_progress',
      created_at: '2026-05-17T00:00:00Z',
      updated_at: '2026-05-17T00:00:00Z',
    }));
    const session = await api.getSession(1);
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/correction/sessions/1',
      expect.objectContaining({ method: 'GET' }),
    );
    expect(session.name).toBe('sess');
  });
});

describe('CorrectionApi.listSegments', () => {
  let api: CorrectionApi;

  beforeEach(() => {
    mockFetch.mockReset();
    api = new CorrectionApi({ baseUrl: '', getToken: () => null });
  });

  it('正確呼叫 GET /sessions/:id/segments 並回傳 array', async () => {
    mockFetch.mockResolvedValueOnce(makeMockResponse([
      {
        id: 1, session_id: 1, segment_index: 0,
        start_sec: 0, end_sec: 5,
        original_text: 'a', corrected_text: null, version: 1,
        updated_at: '2026-05-17T00:00:00Z',
      },
    ]));
    const segments = await api.listSegments(1);
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/correction/sessions/1/segments',
      expect.objectContaining({ method: 'GET' }),
    );
    expect(segments).toHaveLength(1);
    expect(segments[0].segment_index).toBe(0);
  });
});

describe('CorrectionApi.exportToDataset', () => {
  let api: CorrectionApi;

  beforeEach(() => {
    mockFetch.mockReset();
    api = new CorrectionApi({ getToken: () => 'test-token' });
  });

  it('POST body 含 dataset_id（number），回傳 inserted_count 與 dataset_id', async () => {
    const mockResult = {
      inserted_count: 42,
      dataset_id: 5,
    };

    mockFetch.mockResolvedValueOnce(makeMockResponse(mockResult));

    const result = await api.exportToDataset(1, { dataset_id: 5 });

    // 驗證 POST endpoint
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/correction/sessions/1/export-to-dataset',
      expect.objectContaining({
        method: 'POST',
      }),
    );

    // 驗證 body 僅含 dataset_id
    const callArgs = mockFetch.mock.calls[0][1] as RequestInit;
    const body = JSON.parse(callArgs.body as string);
    expect(body).toEqual({ dataset_id: 5 });

    // 驗證回傳值
    expect(result.inserted_count).toBe(42);
    expect(result.dataset_id).toBe(5);
  });
});
