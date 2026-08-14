/**
 * Utility to track hourly card count changes for status badges across CardFlow tables.
 * Snapshots are updated every 1 hour (3600000 ms) in localStorage ('cf_hourly_snapshots_v1').
 */

const STORAGE_KEY = 'cf_hourly_snapshots_v2';
const ONE_HOUR_MS = 3600000;

export function getHourlyChange(entityId, statusKey, currentCount) {
  if (currentCount === undefined || currentCount === null) return 0;
  const count = Number(currentCount) || 0;
  if (!entityId) return 0;

  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const data = raw ? JSON.parse(raw) : {};
    const key = `${entityId}_${statusKey}`;
    const now = Date.now();

    if (!data[key] || (count === 0 && data[key].count > 0)) {
      // Initialize or reset baseline snapshot
      data[key] = { count: count, timestamp: now };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
      return 0;
    }

    const item = data[key];
    // Check if 1 hour has elapsed since last snapshot roll
    if (now - item.timestamp >= ONE_HOUR_MS) {
      const prevCount = item.count;
      data[key] = { count: count, timestamp: now };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
      return count - prevCount;
    }

    // Return change relative to 1-hour snapshot baseline
    return count - item.count;
  } catch (_) {
    return 0;
  }
}
