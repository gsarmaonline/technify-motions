import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
} from "remotion";

export interface BulletsProps {
  title: string;
  points: string[];
  durationSeconds?: number;
}

const FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";

const ACCENT_COLORS = ["#3B82F6", "#10B981", "#F59E0B", "#8B5CF6", "#EF4444", "#06B6D4"];

export const BulletsSlide: React.FC<BulletsProps> = ({ title, points }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleOpacity = interpolate(frame, [0, 18], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(145deg, #EBF2FF 0%, #F5F8FF 55%, #EDF5F0 100%)",
        padding: "80px 100px",
        fontFamily: FONT,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
      }}
    >
      {/* Title */}
      <div
        style={{
          fontSize: 52,
          fontWeight: 800,
          color: "#1E293B",
          opacity: titleOpacity,
          marginBottom: 64,
          letterSpacing: "-0.5px",
          lineHeight: 1.15,
        }}
      >
        {title}
      </div>

      {/* Bullet points */}
      {points.map((point, i) => {
        const startFrame = 20 + i * 16;
        const sc = spring({
          frame: frame - startFrame,
          fps,
          config: { damping: 16, stiffness: 200, mass: 0.7 },
        });
        const opacity = interpolate(frame, [startFrame, startFrame + 12], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        const color = ACCENT_COLORS[i % ACCENT_COLORS.length];

        return (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "flex-start",
              marginBottom: 36,
              opacity,
              transform: `translateX(${(1 - sc) * -50}px)`,
            }}
          >
            {/* Bullet dot */}
            <div
              style={{
                width: 14,
                height: 14,
                borderRadius: "50%",
                background: color,
                marginTop: 11,
                marginRight: 28,
                flexShrink: 0,
                boxShadow: `0 0 0 4px ${color}33`,
              }}
            />
            {/* Text */}
            <div
              style={{
                fontSize: 34,
                color: "#334155",
                lineHeight: 1.5,
                fontWeight: 500,
              }}
            >
              {point}
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
