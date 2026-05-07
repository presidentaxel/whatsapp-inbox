import React from "react";
import "../../styles/axelia-sparkle.css";

/** Marque Axelia à côté des réponses - logo LMDCVTC + halos animés en mode chargement */
export default function SparkleGlyph({ animate = false, className = "" }) {
  return (
    <span
      className={`axelia-sparkle-glyph ${animate ? "axelia-sparkle-glyph--animate" : ""} ${className}`.trim()}
      aria-hidden
    >
      <img
        src="/favicon.svg"
        alt=""
        className="axelia-sparkle-glyph__logo"
        width="22"
        height="22"
      />
      {animate ? (
        <svg
          viewBox="0 0 24 24"
          className="axelia-sparkle-glyph__rings"
          aria-hidden
        >
          {/* Rotation sur groupe SVG : les keyframes transform sur cercle peuvent être ignorées */}
          <g transform="translate(12 12)">
            <g className="axelia-sparkle-glyph__ring-spin axelia-sparkle-glyph__ring-spin--a">
              <circle
                className="axelia-sparkle-glyph__ring axelia-sparkle-glyph__ring--a"
                cx="0"
                cy="0"
                r="10.25"
                fill="none"
                stroke="rgba(255, 255, 255, 0.92)"
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
                stroke="rgba(255, 255, 255, 0.7)"
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
