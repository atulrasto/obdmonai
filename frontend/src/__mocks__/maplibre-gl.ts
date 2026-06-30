// Lightweight stub used by vitest (aliased in vite.config.ts test.alias).
// Prevents WebGL/canvas errors in jsdom.

export class Map {
  constructor(_options: unknown) {}
  addControl() { return this }
  on(_event: string, cb?: () => void) { cb?.(); return this }
  addSource() { return this }
  addLayer() { return this }
  fitBounds() { return this }
  remove() {}
  getCanvas() { return document.createElement('canvas') }
}

export class NavigationControl {
  constructor(_options?: unknown) {}
}

export class Popup {
  constructor(_options?: unknown) {}
  setLngLat() { return this }
  setHTML() { return this }
  addTo() { return this }
  remove() {}
}

export class LngLatBounds {
  extend() { return this }
}
