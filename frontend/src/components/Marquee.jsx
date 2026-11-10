import React from 'react';

export const Marquee = ({
  items,
  reverse = false,
  speedSeconds = 35,
  separatorColor = '#C59A55'
}) => {
  // Duplicate 4 times to ensure continuous seamless loop without visual gaps
  const repeatedItems = [...items, ...items, ...items, ...items];

  return (
    <div
      className="marquee-container w-full py-4 border-y border-white/5 bg-[#0D0F12]/60"
    >
      <div
        className={reverse ? 'marquee-track-reverse' : 'marquee-track'}
        style={{
          animationDuration: `${speedSeconds}s`
        }}
      >
        {repeatedItems.map((item, idx) => (
          <div
            key={idx}
            className="inline-flex items-center mr-8 font-mono text-xs tracking-widest font-medium text-[#A1A4AA] uppercase select-none"
          >
            <span>{item}</span>
            <span
              className="ml-8 text-sm opacity-60"
              style={{ color: separatorColor }}
            >
              /
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
