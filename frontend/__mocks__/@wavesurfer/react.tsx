import React, { useImperativeHandle, forwardRef } from 'react';

export interface FakeWaveSurferRef {
  play: jest.Mock;
  pause: jest.Mock;
  setTime: jest.Mock;
  getCurrentTime: jest.Mock<number, []>;
  getDuration: jest.Mock<number, []>;
}

export const useWavesurfer = jest.fn(() => ({
  wavesurfer: null,
  isReady: false,
  isPlaying: false,
  currentTime: 0,
}));

export default forwardRef<FakeWaveSurferRef, Record<string, unknown>>(
  function FakeWavesurfer(_, ref) {
    useImperativeHandle(ref, () => ({
      play: jest.fn(),
      pause: jest.fn(),
      setTime: jest.fn(),
      getCurrentTime: jest.fn(() => 0),
      getDuration: jest.fn(() => 0),
    }));
    return <div data-testid="fake-wavesurfer" />;
  },
);
