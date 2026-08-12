import React from 'react';

export default function WatermarkLogo() {
  return (
    <div
      className="watermark-logo-container"
      style={{
        position: 'absolute',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        pointerEvents: 'none',
        zIndex: 0,
        opacity: 0.05,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <img
        src="/static/favicon.png"
        onError={(e) => {
          if (!e.target.src.endsWith('/favicon.png')) {
            e.target.src = '/favicon.png';
          }
        }}
        alt="CardFlow Watermark"
        style={{ maxWidth: '280px', width: '35vw', maxHeight: '280px', objectFit: 'contain' }}
      />
    </div>
  );
}
