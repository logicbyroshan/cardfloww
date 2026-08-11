/**
 * Skeleton.jsx — reusable skeleton loading components
 * Uses react-loading-skeleton with dark-navy theme to match the app's color palette.
 * Drop in anywhere you have a `loading` state instead of showing empty tables.
 */
import React from 'react';
import SkeletonBase, { SkeletonTheme } from 'react-loading-skeleton';
import 'react-loading-skeleton/dist/skeleton.css';

// Dark navy theme that matches our .action-bar / sidebar background
const DARK_BASE       = '#1e2538';
const DARK_HIGHLIGHT  = '#2a3250';

// Light white theme for light-background panels (data table rows etc)
const LIGHT_BASE      = '#e8ecf0';
const LIGHT_HIGHLIGHT = '#f1f4f7';

/**
 * SkeletonTableRows — renders N skeleton rows matching our data-table row height.
 * @param {number}  count       Number of skeleton rows to render (default 8)
 * @param {number}  cols        Number of columns (default 6)
 * @param {boolean} dark        Use dark theme (default false — white table bg)
 */
export function SkeletonTableRows({ count = 8, cols = 6, dark = false }) {
  const base      = dark ? DARK_BASE      : LIGHT_BASE;
  const highlight = dark ? DARK_HIGHLIGHT : LIGHT_HIGHLIGHT;

  return (
    <SkeletonTheme baseColor={base} highlightColor={highlight}>
      {Array.from({ length: count }).map((_, i) => (
        <tr key={i} style={{ height: '38px', borderBottom: `1px solid ${dark ? 'rgba(255,255,255,0.06)' : '#f1f5f9'}` }}>
          {Array.from({ length: cols }).map((_, j) => (
            <td key={j} style={{ padding: '8px 12px' }}>
              <SkeletonBase height={14} borderRadius={4} />
            </td>
          ))}
        </tr>
      ))}
    </SkeletonTheme>
  );
}

/**
 * SkeletonCard — a single card-shaped skeleton block.
 */
export function SkeletonCard({ height = 80, dark = false }) {
  const base      = dark ? DARK_BASE      : LIGHT_BASE;
  const highlight = dark ? DARK_HIGHLIGHT : LIGHT_HIGHLIGHT;
  return (
    <SkeletonTheme baseColor={base} highlightColor={highlight}>
      <SkeletonBase height={height} borderRadius={8} />
    </SkeletonTheme>
  );
}

/**
 * SkeletonText — one or more lines of text skeleton.
 */
export function SkeletonText({ lines = 3, dark = false }) {
  const base      = dark ? DARK_BASE      : LIGHT_BASE;
  const highlight = dark ? DARK_HIGHLIGHT : LIGHT_HIGHLIGHT;
  return (
    <SkeletonTheme baseColor={base} highlightColor={highlight}>
      <SkeletonBase count={lines} height={12} borderRadius={4} style={{ marginBottom: '6px' }} />
    </SkeletonTheme>
  );
}

/**
 * SkeletonStatCards — 4 inline stat cards like on the server snapshot panel.
 */
export function SkeletonStatCards({ count = 4, dark = false }) {
  const base      = dark ? DARK_BASE      : LIGHT_BASE;
  const highlight = dark ? DARK_HIGHLIGHT : LIGHT_HIGHLIGHT;
  return (
    <SkeletonTheme baseColor={base} highlightColor={highlight}>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${count}, 1fr)`, gap: '12px', padding: '12px 16px' }}>
        {Array.from({ length: count }).map((_, i) => (
          <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '12px', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px' }}>
            <SkeletonBase height={12} width="60%" borderRadius={4} />
            <SkeletonBase height={24} width="80%" borderRadius={4} />
            <SkeletonBase height={10} width="50%" borderRadius={4} />
          </div>
        ))}
      </div>
    </SkeletonTheme>
  );
}

export default SkeletonBase;
