"use client";

import { useMemo } from "react";
import { drainMinFor, formatMinutes } from "./model";

interface DrainChartProps {
  users: number;
  workers: number;
  jobSec: number;
}

const MAX_WORKERS = 60;
const W = 600;
const H = 260;
const PAD = { top: 20, right: 18, bottom: 30, left: 56 };
const CURVE_COLOR = "#a78bfa";

/**
 * SVG chart of queue drain time vs warm worker count (log-y scale),
 * with a marker at the currently selected worker count.
 */
export function DrainChart({ users, workers, jobSec }: DrainChartProps) {
  const { path, xFor, ticks, current, cx, cy, warmY } = useMemo(() => {
    const innerW = W - PAD.left - PAD.right;
    const innerH = H - PAD.top - PAD.bottom;

    const vals: number[] = [];
    for (let w = 1; w <= MAX_WORKERS; w++) {
      vals.push(drainMinFor(users, w, jobSec));
    }
    const yMin = Math.min(...vals);
    const yMax = Math.max(...vals);
    const logMin = Math.log10(Math.max(yMin, 1e-6));
    const logMax = Math.log10(yMax);
    const span = logMax - logMin || 1;

    const xFor = (w: number) => PAD.left + ((w - 1) / (MAX_WORKERS - 1)) * innerW;
    const yFor = (v: number) => PAD.top + (1 - (Math.log10(Math.max(v, 1e-6)) - logMin) / span) * innerH;

    const pts = vals.map((v, i) => ({ x: xFor(i + 1), y: yFor(v), v }));
    const p = pts
      .map((pt, i) => `${i === 0 ? "M" : "L"}${pt.x.toFixed(1)},${pt.y.toFixed(1)}`)
      .join(" ");

    const ticks: { v: number; y: number }[] = [];
    for (let e = Math.floor(logMin); e <= Math.ceil(logMax); e++) {
      const v = Math.pow(10, e);
      if (v >= yMin * 0.5 && v <= yMax * 2) ticks.push({ v, y: yFor(v) });
    }

    const current = drainMinFor(users, workers, jobSec);
    return {
      path: p,
      xFor,
      yFor,
      ticks,
      current,
      cx: xFor(workers),
      cy: yFor(current),
      warmY: yFor(5),
    };
  }, [users, workers, jobSec]);

  const labelAnchor =
    cx < PAD.left + 24 ? "start" : cx > W - PAD.right - 24 ? "end" : "middle";
  const labelX =
    cx < PAD.left + 24 ? cx + 6 : cx > W - PAD.right - 24 ? cx - 6 : cx;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-auto w-full"
      role="img"
      aria-label={`Queue drain time vs warm worker count. Current: ${formatMinutes(current)} at ${workers} workers.`}
    >
      {/* y-axis title */}
      <text x={PAD.left} y={12} fontSize="10" fill="rgba(156,163,175,0.9)">
        drain (min, log)
      </text>

      {/* horizontal gridlines + tick labels */}
      {ticks.map((t) => (
        <g key={t.v}>
          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={t.y}
            y2={t.y}
            stroke="rgba(255,255,255,0.06)"
            strokeDasharray="3 3"
          />
          <text x={PAD.left - 8} y={t.y + 3} textAnchor="end" fontSize="10" fill="rgba(156,163,175,0.9)">
            {formatMinutes(t.v)}
          </text>
        </g>
      ))}

      {/* 5-minute warm window reference */}
      <line
        x1={PAD.left}
        x2={W - PAD.right}
        y1={warmY}
        y2={warmY}
        stroke="rgba(251,191,36,0.35)"
        strokeDasharray="4 4"
      />
      <text x={W - PAD.right} y={warmY - 6} textAnchor="end" fontSize="9" fill="rgba(251,191,36,0.75)">
        5-min warm window
      </text>

      {/* drain curve */}
      <path d={path} fill="none" stroke={CURVE_COLOR} strokeWidth="2" strokeLinejoin="round" />

      {/* current worker marker */}
      <line
        x1={cx}
        x2={cx}
        y1={PAD.top}
        y2={H - PAD.bottom}
        stroke="rgba(167,139,250,0.35)"
        strokeDasharray="3 3"
      />
      <circle cx={cx} cy={cy} r="5" fill={CURVE_COLOR} stroke="#12122a" strokeWidth="2" />
      <text
        x={labelX}
        y={Math.max(cy - 10, 14)}
        textAnchor={labelAnchor}
        fontSize="10"
        fill="#c4b5fd"
      >
        {formatMinutes(current)}
      </text>

      {/* x-axis labels */}
      <text x={PAD.left} y={H - 8} fontSize="10" fill="rgba(156,163,175,0.9)">
        1
      </text>
      <text x={xFor(30)} y={H - 8} textAnchor="middle" fontSize="10" fill="rgba(156,163,175,0.9)">
        30
      </text>
      <text x={xFor(MAX_WORKERS)} y={H - 8} textAnchor="end" fontSize="10" fill="rgba(156,163,175,0.9)">
        {MAX_WORKERS} workers
      </text>
    </svg>
  );
}
