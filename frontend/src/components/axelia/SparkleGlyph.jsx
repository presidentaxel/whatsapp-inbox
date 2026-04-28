import React from "react";
import "../../styles/axelia-sparkle.css";

/** Petit symbole type Gemini — étoile + arc anime en mode « chargement » */
export default function SparkleGlyph({ animate = false, className = "" }) {
  const uid = React.useId().replace(/:/g, "");
  const gradId = `axeliaSparkGrad-${uid}`;

  return (
    <span
      className={`axelia-sparkle-glyph ${animate ? "axelia-sparkle-glyph--animate" : ""} ${className}`.trim()}
      aria-hidden
    >
      <svg viewBox="0 0 24 24" width="22" height="22" className="axelia-sparkle-glyph__star">
        <defs>
          <linearGradient id={gradId} x1="50%" y1="100%" x2="50%" y2="0%">
            <stop offset="0%" stopColor="#4285f4" />
            <stop offset="100%" stopColor="#8ab4f8" />
          </linearGradient>
        </defs>
        <path
          fill={`url(#${gradId})`}
          d="M12 2.5l2.06 6.35h6.68l-5.41 3.93 2.07 6.37L12 15.62l-5.4 3.92 2.07-6.37L3.26 8.85h6.68L12 2.5z"
        />
      </svg>
      {animate && (
        <svg viewBox="0 0 24 24" className="axelia-sparkle-glyph__orbit" aria-hidden>
          <circle
            cx="12"
            cy="4"
            r="2.2"
            fill="none"
            stroke="#8ab4f8"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        </svg>
      )}
    </span>
  );
}
