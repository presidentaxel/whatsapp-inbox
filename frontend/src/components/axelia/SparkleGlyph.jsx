import React from "react";
import "../../styles/axelia-sparkle.css";

/** Marque Axelia à côté des réponses - étoile + halos animés en mode chargement */
export default function SparkleGlyph({ animate = false, className = "" }) {
  const uid = React.useId().replace(/:/g, "");
  const starGradId = `axeliaSparkStar-${uid}`;
  const ringGradId = `axeliaSparkRing-${uid}`;

  return (
    <span
      className={`axelia-sparkle-glyph ${animate ? "axelia-sparkle-glyph--animate" : ""} ${className}`.trim()}
      aria-hidden
    >
      <svg viewBox="0 0 24 24" width="22" height="22" className="axelia-sparkle-glyph__star">
        <defs>
          <linearGradient id={starGradId} x1="50%" y1="100%" x2="50%" y2="0%">
            <stop offset="0%" stopColor="#4285f4" />
            <stop offset="55%" stopColor="#7baaf7" />
            <stop offset="100%" stopColor="#c4d7ff" />
          </linearGradient>
        </defs>
        <path
          fill={`url(#${starGradId})`}
          d="M12 2.5l2.06 6.35h6.68l-5.41 3.93 2.07 6.37L12 15.62l-5.4 3.92 2.07-6.37L3.26 8.85h6.68L12 2.5z"
        />
      </svg>
      {animate ? (
        <svg
          viewBox="0 0 24 24"
          className="axelia-sparkle-glyph__rings"
          aria-hidden
        >
          <defs>
            <linearGradient
              id={ringGradId}
              x1="0%"
              y1="0%"
              x2="100%"
              y2="100%"
            >
              <stop offset="0%" stopColor="#66a3ff" stopOpacity="0.15" />
              <stop offset="40%" stopColor="#8ab4f8" stopOpacity="0.95" />
              <stop offset="100%" stopColor="#b8c9ff" stopOpacity="0.35" />
            </linearGradient>
          </defs>
          {/* Rotation sur groupe SVG : les keyframes transform sur cercle peuvent être ignorées */}
          <g transform="translate(12 12)">
            <g className="axelia-sparkle-glyph__ring-spin axelia-sparkle-glyph__ring-spin--a">
              <circle
                className="axelia-sparkle-glyph__ring axelia-sparkle-glyph__ring--a"
                cx="0"
                cy="0"
                r="10.25"
                fill="none"
                stroke={`url(#${ringGradId})`}
                strokeWidth="1.65"
                strokeLinecap="round"
              />
            </g>
          </g>
          <g transform="translate(12 12)">
            <g className="axelia-sparkle-glyph__ring-spin axelia-sparkle-glyph__ring-spin--b">
              <circle
                className="axelia-sparkle-glyph__ring axelia-sparkle-glyph__ring--b"
                cx="0"
                cy="0"
                r="9.15"
                fill="none"
                stroke="rgba(180, 210, 255, 0.55)"
                strokeWidth="1.15"
                strokeLinecap="round"
              />
            </g>
          </g>
        </svg>
      ) : null}
    </span>
  );
}
