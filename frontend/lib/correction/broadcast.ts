/**
 * Cross-tab sync via BroadcastChannel. Same-session only.
 * Channel name 含 sessionId 避免不同 session 互相干擾。
 * jsdom / 舊瀏覽器環境無 BroadcastChannel 時降級為 no-op。
 */

export interface CorrectionBroadcastEvent {
  type: 'segment_saved';
  segmentId: number;
  version: number;
}

export function createCorrectionChannel(sessionId: number) {
  if (typeof BroadcastChannel === 'undefined') {
    // no-op fallback for jsdom / legacy browsers
    return {
      post: (_: CorrectionBroadcastEvent) => {},
      subscribe: (_: (e: CorrectionBroadcastEvent) => void) => () => {},
      close: () => {},
    };
  }

  const ch = new BroadcastChannel(`correction:${sessionId}`);

  return {
    post: (event: CorrectionBroadcastEvent) => ch.postMessage(event),
    subscribe: (cb: (e: CorrectionBroadcastEvent) => void) => {
      const handler = (msg: MessageEvent<CorrectionBroadcastEvent>) => cb(msg.data);
      ch.addEventListener('message', handler);
      return () => ch.removeEventListener('message', handler);
    },
    close: () => ch.close(),
  };
}
