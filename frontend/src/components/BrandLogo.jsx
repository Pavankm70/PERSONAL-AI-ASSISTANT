import React from 'react';
import { BRAND_CONFIG } from '../config/brand';

export const BrandLogo = ({
  size = 'md',
  showText = true,
  className = ''
}) => {
  const iconSizes = {
    sm: 24,
    md: 32,
    lg: 42
  };

  const px = iconSizes[size] || 32;

  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.75rem', textDecoration: 'none' }} className={className}>
      {/* Geometric orbital emblem */}
      <div
        style={{
          width: px,
          height: px,
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'linear-gradient(135deg, rgba(197, 154, 85, 0.2) 0%, rgba(18, 20, 24, 0.8) 100%)',
          borderRadius: size === 'sm' ? '6px' : '9px',
          border: '1px solid rgba(197, 154, 85, 0.4)',
          boxShadow: '0 0 16px rgba(197, 154, 85, 0.2)',
          flexShrink: 0
        }}
      >
        <svg
          width={px * 0.65}
          height={px * 0.65}
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          {/* Inner core */}
          <circle cx="12" cy="12" r="3" fill="#E6C17A" />
          {/* Orbital diamond */}
          <path
            d="M12 2L21 12L12 21L3 12L12 2Z"
            stroke="#C59A55"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {/* Connected nodes */}
          <circle cx="12" cy="2" r="1.5" fill="#FFF7ED" />
          <circle cx="21" cy="12" r="1.5" fill="#FFF7ED" />
          <circle cx="12" cy="21" r="1.5" fill="#FFF7ED" />
          <circle cx="3" cy="12" r="1.5" fill="#FFF7ED" />
        </svg>
      </div>

      {showText && (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span
            style={{
              fontFamily: 'var(--font-sans)',
              letterSpacing: '0.12em',
              fontWeight: 700,
              color: 'var(--text-primary)',
              fontSize: size === 'sm' ? '0.9rem' : size === 'lg' ? '1.35rem' : '1.05rem',
              lineHeight: 1.1
            }}
          >
            {BRAND_CONFIG.name}
          </span>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.62rem',
              color: 'var(--gold-warm)',
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              opacity: 0.85
            }}
          >
            INTELLIGENCE
          </span>
        </div>
      )}
    </div>
  );
};
