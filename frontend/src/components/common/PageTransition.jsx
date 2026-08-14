import React from 'react';
import { AnimatePresence, motion } from 'framer-motion';

/**
 * PageTransition — wraps each page with a smooth swipe-up animation
 * on every route/tab change. Powered by Framer Motion AnimatePresence.
 * Visual output is identical to the previous CSS-based transition.
 */
export default function PageTransition({ pageKey, children, fullHeight = false }) {
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={pageKey}
        initial={{ opacity: 0, y: 45 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -25 }}
        transition={{
          opacity: { duration: 0.32, ease: [0.16, 1, 0.3, 1] },
          y: { duration: 0.32, ease: [0.16, 1, 0.3, 1] },
        }}
        style={{
          flex: 1,
          height: '100%',
          width: '100%',
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
          overflow: 'hidden',
        }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
