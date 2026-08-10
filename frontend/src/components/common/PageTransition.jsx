import React, { useRef, useEffect, useState } from 'react';

/**
 * PageTransition — wraps each page with a smooth fade+lift animation
 * on every route/tab change. Triggered by the `pageKey` prop.
 */
export default function PageTransition({ pageKey, children, fullHeight = false }) {
  const [animKey, setAnimKey] = useState(pageKey);
  const [visible, setVisible] = useState(true);
  const prevKey = useRef(pageKey);

  useEffect(() => {
    if (pageKey !== prevKey.current) {
      // Quick swipe-up exit (100ms), then swap content and swipe-up enter (320ms)
      setVisible(false);
      const t = setTimeout(() => {
        prevKey.current = pageKey;
        setAnimKey(pageKey);
        setVisible(true);
      }, 100);
      return () => clearTimeout(t);
    }
  }, [pageKey]);

  return (
    <div
      key={animKey}
      className={visible ? 'page-transition-enter' : 'page-transition-exit'}
      style={fullHeight ? { height: '100%', width: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' } : { flex: 1, minHeight: 0, width: '100%' }}
    >
      {children}
    </div>
  );
}
