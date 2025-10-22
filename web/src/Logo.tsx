import React from 'react';

interface LogoProps {
  size?: number;
}

const Logo: React.FC<LogoProps> = ({ size = 40 }) => {
  const dimension = `${size}px`;

  return (
    <div
      aria-label="SF Rec Events logo"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: dimension,
        height: dimension,
        borderRadius: '12px',
        background: 'linear-gradient(135deg, #1b5e20 0%, #66bb6a 60%, #a5d6a7 100%)',
        boxShadow: '0 4px 10px rgba(0, 0, 0, 0.18)',
      }}
    >
      <svg
        viewBox="0 0 64 64"
        role="img"
        aria-hidden="true"
        focusable="false"
        style={{ width: '70%', height: '70%' }}
      >
        <defs>
          <linearGradient id="leafGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#dcedc8" />
            <stop offset="100%" stopColor="#81c784" />
          </linearGradient>
        </defs>
        <path
          d="M12 34c8-14 22-22 40-20C50 32 34 44 20 52c-6-4-10-10-8-18z"
          fill="url(#leafGradient)"
        />
        <path
          d="M22 46c4-8 12-14 22-16"
          stroke="#2e7d32"
          strokeWidth="4"
          strokeLinecap="round"
          fill="none"
        />
      </svg>
    </div>
  );
};

export default Logo;

