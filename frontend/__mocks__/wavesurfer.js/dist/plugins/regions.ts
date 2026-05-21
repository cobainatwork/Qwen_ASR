// Manual mock for wavesurfer.js/dist/plugins/regions
// jsdom has no AudioContext; this stub prevents import errors in unit tests.

const RegionsPlugin = {
  create: jest.fn(() => ({
    addRegion: jest.fn(),
    on: jest.fn(),
    destroy: jest.fn(),
    getRegions: jest.fn(() => []),
  })),
};

export default RegionsPlugin;
