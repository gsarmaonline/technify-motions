import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  interpolate,
} from "remotion";

export interface CodeProps {
  title: string;
  language: string;
  code: string;
  durationSeconds?: number;
}

const FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
const CODE_FONT = "'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace";

// Minimal keyword highlighting by language
function tokenize(line: string, language: string): React.ReactNode {
  const keywords: Record<string, string[]> = {
    python:     ["def", "class", "import", "from", "return", "if", "else", "elif", "for", "while", "in", "not", "and", "or", "True", "False", "None", "with", "as", "try", "except", "raise", "lambda", "yield", "async", "await"],
    javascript: ["function", "const", "let", "var", "return", "if", "else", "for", "while", "class", "import", "export", "from", "default", "async", "await", "new", "this", "true", "false", "null", "undefined"],
    go:         ["func", "package", "import", "var", "const", "type", "struct", "interface", "return", "if", "else", "for", "range", "go", "chan", "select", "case", "defer", "map", "make", "nil", "true", "false"],
    sql:        ["SELECT", "FROM", "WHERE", "JOIN", "LEFT", "RIGHT", "INNER", "ON", "GROUP", "BY", "ORDER", "HAVING", "INSERT", "INTO", "VALUES", "UPDATE", "SET", "DELETE", "CREATE", "TABLE", "INDEX", "AND", "OR", "NOT", "NULL", "AS", "LIMIT", "OFFSET"],
    bash:       ["if", "then", "else", "fi", "for", "do", "done", "while", "echo", "export", "cd", "ls", "grep", "awk", "sed", "cat", "rm", "mkdir", "chmod"],
    yaml:       [],
    text:       [],
  };
  const kws = new Set((keywords[language] || []).map(k => k.toLowerCase()));

  // Split on word boundaries for simple highlighting
  const parts = line.split(/(\s+|[(){}[\],.:;=<>!+\-*/%|&^~"'`])/);
  return (
    <>
      {parts.map((part, i) => {
        if (kws.has(part.toLowerCase())) {
          return <span key={i} style={{ color: "#7DD3FC", fontWeight: 600 }}>{part}</span>;
        }
        if (/^["'`].*["'`]$/.test(part) || /^["'`]/.test(part)) {
          return <span key={i} style={{ color: "#86EFAC" }}>{part}</span>;
        }
        if (/^\d+$/.test(part)) {
          return <span key={i} style={{ color: "#FCA5A5" }}>{part}</span>;
        }
        if (part.startsWith("#") || part.startsWith("//")) {
          return <span key={i} style={{ color: "#94A3B8", fontStyle: "italic" }}>{part}</span>;
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

export const CodeSlide: React.FC<CodeProps> = ({ title, language, code }) => {
  const frame = useCurrentFrame();

  const titleOpacity = interpolate(frame, [0, 18], [0, 1], {
    extrapolateRight: "clamp",
  });

  const lines = code.split("\n");

  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(145deg, #0F172A 0%, #1E293B 100%)",
        padding: "72px 90px",
        fontFamily: FONT,
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Title + language badge */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 20,
          marginBottom: 48,
          opacity: titleOpacity,
        }}
      >
        <div style={{ fontSize: 46, fontWeight: 800, color: "#F8FAFC", letterSpacing: "-0.4px" }}>
          {title}
        </div>
        <div
          style={{
            fontSize: 18,
            fontWeight: 600,
            color: "#7DD3FC",
            background: "#0EA5E920",
            border: "1px solid #0EA5E940",
            borderRadius: 8,
            padding: "4px 14px",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            marginTop: 4,
          }}
        >
          {language}
        </div>
      </div>

      {/* Code block */}
      <div
        style={{
          background: "#0D1B2A",
          borderRadius: 16,
          padding: "40px 44px",
          border: "1px solid #334155",
          flex: 1,
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
        }}
      >
        {lines.map((line, i) => {
          const startFrame = 22 + i * 4;
          const opacity = interpolate(frame, [startFrame, startFrame + 8], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          return (
            <div
              key={i}
              style={{
                fontSize: Math.max(20, 28 - Math.floor(lines.length / 4)),
                color: "#E2E8F0",
                lineHeight: 1.75,
                opacity,
                whiteSpace: "pre",
                fontFamily: CODE_FONT,
              }}
            >
              {/* Line number */}
              <span style={{ color: "#475569", marginRight: 28, userSelect: "none", fontSize: "0.75em" }}>
                {String(i + 1).padStart(2, " ")}
              </span>
              {tokenize(line || " ", language)}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
