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
      // Quick fade-out, then swap content and fade-in
      setVisible(false);
      const t = setTimeout(() => {
        prevKey.current = pageKey;
        setAnimKey(pageKey);
        setVisible(true);
      }, 80); // 80ms out, then 280ms in via CSS
      return () => clearTimeout(t);
    }
  }, [pageKey]);

  return (
    <div
      key={animKey}
      className={visible ? 'page-transition-enter' : 'page-transition-exit'}
      style={fullHeight ? { height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' } : { flex: 1, minHeight: 0 }}
    >
      {children}
    </div>
  );
}
