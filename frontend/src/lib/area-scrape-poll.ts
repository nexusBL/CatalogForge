export type ScrapeTickLock = { current: boolean };

export function claimScrapeTick(inFlight: ScrapeTickLock): boolean {
  if (inFlight.current) {
    return false;
  }
  inFlight.current = true;
  return true;
}

export function releaseScrapeTick(inFlight: ScrapeTickLock): void {
  inFlight.current = false;
}
