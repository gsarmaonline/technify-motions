import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
} from "remotion";
import * as Dagre from "@dagrejs/dagre";

// ── Types ────────────────────────────────────────────────────────────────────

export type NodeShape = "box" | "diamond" | "circle" | "rounded";

export interface NodeData {
  id: string;
  label: string;
  shape: NodeShape;
}

export interface EdgeData {
  from: string;
  to: string;
  label?: string;
}

export interface GraphProps {
  nodes: NodeData[];
  edges: EdgeData[];
  title?: string;
  durationSeconds?: number;
}

// ── Layout constants ─────────────────────────────────────────────────────────

const NODE_W = 190;
const NODE_H = 60;
const DIAMOND_W = 160;
const DIAMOND_H = 100;

// ── Colour palette ───────────────────────────────────────────────────────────

const C = {
  bg: "#EFF3FF",
  box: { fill: "#3B82F6", stroke: "#1D4ED8", text: "#FFFFFF" },
  diamond: { fill: "#F59E0B", stroke: "#B45309", text: "#FFFFFF" },
  circle: { fill: "#10B981", stroke: "#047857", text: "#FFFFFF" },
  rounded: { fill: "#8B5CF6", stroke: "#6D28D9", text: "#FFFFFF" },
  edge: "#475569",
  edgeLabel: { fill: "#FFFFFF", stroke: "#94A3B8", text: "#334155" },
  title: "#1E293B",
  shadow: "rgba(0,0,0,0.18)",
};

// ── Dagre layout ─────────────────────────────────────────────────────────────

interface LayoutNode extends NodeData {
  x: number;
  y: number;
  w: number;
  h: number;
}
interface LayoutEdge extends EdgeData {
  points: { x: number; y: number }[];
}

function computeLayout(nodes: NodeData[], edges: EdgeData[]) {
  const g = new Dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", ranksep: 90, nodesep: 70, marginx: 60, marginy: 60 });
  g.setDefaultEdgeLabel(() => ({}));

  nodes.forEach((n) => {
    const isDiamond = n.shape === "diamond";
    g.setNode(n.id, {
      width: isDiamond ? DIAMOND_W : NODE_W,
      height: isDiamond ? DIAMOND_H : NODE_H,
    });
  });

  const validEdgeIds = new Set(nodes.map((n) => n.id));
  edges.forEach((e) => {
    if (validEdgeIds.has(e.from) && validEdgeIds.has(e.to)) {
      g.setEdge(e.from, e.to);
    }
  });

  Dagre.layout(g);

  const laidOutNodes: LayoutNode[] = nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      ...n,
      x: pos?.x ?? 0,
      y: pos?.y ?? 0,
      w: pos?.width ?? NODE_W,
      h: pos?.height ?? NODE_H,
    };
  });

  const laidOutEdges: LayoutEdge[] = edges
    .filter((e) => validEdgeIds.has(e.from) && validEdgeIds.has(e.to))
    .map((e) => {
      let points: { x: number; y: number }[] = [];
      try {
        const info = g.edge(e.from, e.to);
        points = info?.points ?? [];
      } catch {}
      if (points.length < 2) {
        const a = g.node(e.from);
        const b = g.node(e.to);
        points = [
          { x: a?.x ?? 0, y: a?.y ?? 0 },
          { x: b?.x ?? 0, y: b?.y ?? 0 },
        ];
      }
      return { ...e, points };
    });

  return { nodes: laidOutNodes, edges: laidOutEdges };
}

// ── SVG path helpers ─────────────────────────────────────────────────────────

function toSmoothPath(pts: { x: number; y: number }[]): string {
  if (pts.length === 0) return "";
  if (pts.length === 1) return `M ${pts[0].x} ${pts[0].y}`;
  if (pts.length === 2) return `M ${pts[0].x} ${pts[0].y} L ${pts[1].x} ${pts[1].y}`;

  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const mid = {
      x: (pts[i].x + pts[i + 1].x) / 2,
      y: (pts[i].y + pts[i + 1].y) / 2,
    };
    d += ` Q ${pts[i].x} ${pts[i].y} ${mid.x} ${mid.y}`;
  }
  d += ` L ${pts[pts.length - 1].x} ${pts[pts.length - 1].y}`;
  return d;
}

// ── Text helpers ─────────────────────────────────────────────────────────────

function wrapLabel(label: string, maxChars = 20): string[] {
  if (label.length <= maxChars) return [label];
  const words = label.split(/\s+/);
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    const candidate = cur ? `${cur} ${w}` : w;
    if (candidate.length > maxChars) {
      if (cur) lines.push(cur);
      cur = w.length > maxChars ? w.slice(0, maxChars - 1) + "…" : w;
    } else {
      cur = candidate;
    }
  }
  if (cur) lines.push(cur);
  return lines.slice(0, 2); // max 2 lines
}

// ── Node component ───────────────────────────────────────────────────────────

const FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
const DASH_MAX = 5000; // larger than any visible path

const AnimatedNode: React.FC<{
  node: LayoutNode;
  startFrame: number;
  fps: number;
  frame: number;
}> = ({ node, startFrame, fps, frame }) => {
  if (frame < startFrame) return null;

  const sc = spring({
    frame: frame - startFrame,
    fps,
    config: { damping: 14, stiffness: 220, mass: 0.65 },
  });

  const color =
    node.shape === "diamond"
      ? C.diamond
      : node.shape === "circle"
      ? C.circle
      : node.shape === "rounded"
      ? C.rounded
      : C.box;

  const hw = node.w / 2;
  const hh = node.h / 2;
  const lines = wrapLabel(node.label, 22);
  const lineH = 17;
  const textY0 = -((lines.length - 1) * lineH) / 2;

  const textEl = lines.map((line, i) => (
    <text
      key={i}
      textAnchor="middle"
      x={0}
      y={textY0 + i * lineH}
      dominantBaseline="central"
      fontSize={14}
      fontWeight={600}
      fill={color.text}
      fontFamily={FONT}
    >
      {line}
    </text>
  ));

  return (
    <g transform={`translate(${node.x}, ${node.y}) scale(${sc})`}>
      {/* Drop shadow */}
      <filter id={`sh-${node.id}`} x="-30%" y="-30%" width="160%" height="160%">
        <feDropShadow dx="0" dy="3" stdDeviation="4" floodColor={C.shadow} />
      </filter>

      {node.shape === "diamond" ? (
        <polygon
          points={`0,${-hh} ${hw},0 0,${hh} ${-hw},0`}
          fill={color.fill}
          stroke={color.stroke}
          strokeWidth={2.5}
          filter={`url(#sh-${node.id})`}
        />
      ) : node.shape === "circle" ? (
        <circle
          r={Math.min(hw, hh)}
          fill={color.fill}
          stroke={color.stroke}
          strokeWidth={2.5}
          filter={`url(#sh-${node.id})`}
        />
      ) : (
        <rect
          x={-hw}
          y={-hh}
          width={node.w}
          height={node.h}
          rx={node.shape === "rounded" ? 30 : 8}
          fill={color.fill}
          stroke={color.stroke}
          strokeWidth={2.5}
          filter={`url(#sh-${node.id})`}
        />
      )}
      {textEl}
    </g>
  );
};

// ── Edge component ───────────────────────────────────────────────────────────

const AnimatedEdge: React.FC<{
  edge: LayoutEdge;
  startFrame: number;
  animFrames: number;
  frame: number;
}> = ({ edge, startFrame, animFrames, frame }) => {
  const progress = interpolate(frame, [startFrame, startFrame + animFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (progress <= 0) return null;

  const d = toSmoothPath(edge.points);
  const mid = edge.points[Math.floor(edge.points.length / 2)] ?? edge.points[0];

  return (
    <g>
      <path
        d={d}
        fill="none"
        stroke={C.edge}
        strokeWidth={2.2}
        strokeDasharray={DASH_MAX}
        strokeDashoffset={DASH_MAX * (1 - progress)}
        markerEnd="url(#arrowhead)"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {edge.label && progress > 0.65 && mid && (
        <g
          transform={`translate(${mid.x + 6}, ${mid.y - 14})`}
          opacity={interpolate(progress, [0.65, 1], [0, 1])}
        >
          <rect x={-28} y={-11} width={56} height={22} rx={5} fill={C.edgeLabel.fill} stroke={C.edgeLabel.stroke} strokeWidth={1} />
          <text
            textAnchor="middle"
            dominantBaseline="central"
            fontSize={12}
            fill={C.edgeLabel.text}
            fontFamily={FONT}
            fontWeight={500}
          >
            {edge.label.length > 10 ? edge.label.slice(0, 9) + "…" : edge.label}
          </text>
        </g>
      )}
    </g>
  );
};

// ── Main composition ─────────────────────────────────────────────────────────

export const FlowchartAnimation: React.FC<GraphProps> = ({
  nodes,
  edges,
  title,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width, height } = useVideoConfig();

  const layout = computeLayout(nodes, edges);

  // ── Fit graph into canvas ──────────────────────────────────────────────────
  const TITLE_H = title ? 90 : 0;
  const PAD = 60;

  let viewBox = { minX: 0, maxX: NODE_W, minY: 0, maxY: NODE_H };
  if (layout.nodes.length > 0) {
    const xs = layout.nodes.flatMap((n) => [n.x - n.w / 2, n.x + n.w / 2]);
    const ys = layout.nodes.flatMap((n) => [n.y - n.h / 2, n.y + n.h / 2]);
    viewBox = {
      minX: Math.min(...xs),
      maxX: Math.max(...xs),
      minY: Math.min(...ys),
      maxY: Math.max(...ys),
    };
  }

  const graphW = viewBox.maxX - viewBox.minX + PAD * 2;
  const graphH = viewBox.maxY - viewBox.minY + PAD * 2;
  const availW = width;
  const availH = height - TITLE_H;

  const scale = Math.min((availW * 0.88) / graphW, (availH * 0.9) / graphH, 1.6);
  const scaledW = graphW * scale;
  const scaledH = graphH * scale;

  const tx = (availW - scaledW) / 2 - viewBox.minX * scale + PAD * scale;
  const ty = TITLE_H + (availH - scaledH) / 2 - viewBox.minY * scale + PAD * scale;

  // ── Animation timing ───────────────────────────────────────────────────────
  // Sort nodes by their y position (top→bottom = dagre's rank order)
  const orderedIds = [...layout.nodes]
    .sort((a, b) => a.y - b.y || a.x - b.x)
    .map((n) => n.id);

  const nodeInterval = Math.max(
    fps * 0.18,
    (durationInFrames * 0.55) / Math.max(orderedIds.length, 1)
  );

  const nodeStartFrames: Record<string, number> = {};
  orderedIds.forEach((id, i) => {
    nodeStartFrames[id] = Math.round(i * nodeInterval + 6);
  });

  const EDGE_ANIM_FRAMES = Math.round(fps * 0.42);
  const edgeStartFrames = layout.edges.map((e) => {
    const a = nodeStartFrames[e.from] ?? 0;
    const b = nodeStartFrames[e.to] ?? 0;
    return Math.round(Math.max(a, b) + fps * 0.18);
  });

  // ── Title fade-in ──────────────────────────────────────────────────────────
  const titleOpacity = interpolate(frame, [0, 18], [0, 1], {
    extrapolateRight: "clamp",
  });

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(145deg, #EBF2FF 0%, #F5F8FF 55%, #EDF5F0 100%)`,
        overflow: "hidden",
        fontFamily: FONT,
      }}
    >
      {/* Title */}
      {title && (
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: TITLE_H,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            opacity: titleOpacity,
            fontSize: 34,
            fontWeight: 700,
            color: C.title,
            letterSpacing: "-0.4px",
            padding: "0 80px",
            textAlign: "center",
          }}
        >
          {title}
        </div>
      )}

      <svg
        width={width}
        height={height}
        style={{ position: "absolute", top: 0, left: 0, overflow: "visible" }}
      >
        <defs>
          <marker
            id="arrowhead"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M 0 1.5 L 8.5 5 L 0 8.5 Z" fill={C.edge} />
          </marker>
        </defs>

        <g transform={`translate(${tx}, ${ty}) scale(${scale})`}>
          {/* Edges drawn first (under nodes) */}
          {layout.edges.map((edge, i) => (
            <AnimatedEdge
              key={`e-${i}`}
              edge={edge}
              startFrame={edgeStartFrames[i]}
              animFrames={EDGE_ANIM_FRAMES}
              frame={frame}
            />
          ))}

          {/* Nodes on top */}
          {layout.nodes.map((node) => (
            <AnimatedNode
              key={node.id}
              node={node}
              startFrame={nodeStartFrames[node.id] ?? 0}
              fps={fps}
              frame={frame}
            />
          ))}
        </g>
      </svg>
    </AbsoluteFill>
  );
};
