// Manual mock: jsdom doesn't have AudioContext / MediaSource, this file returns a fake
// with minimal interface to let components render without error in test environment.

export interface FakeWaveSurfer {
  on: jest.Mock;
  off: jest.Mock;
  play: jest.Mock;
  pause: jest.Mock;
  setTime: jest.Mock;
  setPlaybackRate: jest.Mock;
  setVolume: jest.Mock;
  getDuration: jest.Mock<number, []>;
  getCurrentTime: jest.Mock<number, []>;
  destroy: jest.Mock;
  load: jest.Mock<Promise<void>, [string]>;
  zoom: jest.Mock;
}

const factory = jest.fn((): FakeWaveSurfer => ({
  on: jest.fn(),
  off: jest.fn(),
  play: jest.fn(),
  pause: jest.fn(),
  setTime: jest.fn(),
  setPlaybackRate: jest.fn(),
  setVolume: jest.fn(),
  getDuration: jest.fn(() => 0),
  getCurrentTime: jest.fn(() => 0),
  destroy: jest.fn(),
  load: jest.fn((_url: string) => Promise.resolve()),
  zoom: jest.fn(),
}));

export default { create: factory };
