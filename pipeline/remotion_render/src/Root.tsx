import React from "react";
import { Composition } from "remotion";
import { FlowchartAnimation, type GraphProps } from "./FlowchartAnimation";
import { BulletsSlide, type BulletsProps } from "./BulletsSlide";
import { CodeSlide, type CodeProps } from "./CodeSlide";

const calculateMetadata = ({ props }: { props: { durationSeconds?: number } }) => ({
  durationInFrames: Math.max(90, Math.round((props.durationSeconds ?? 5) * 30)),
});

export const Root: React.FC = () => {
  return (
    <>
      <Composition
        id="FlowchartAnimation"
        component={FlowchartAnimation}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ nodes: [], edges: [], title: "", durationSeconds: 5 } as GraphProps}
        calculateMetadata={calculateMetadata}
      />
      <Composition
        id="BulletsSlide"
        component={BulletsSlide}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ title: "", points: [], durationSeconds: 5 } as BulletsProps}
        calculateMetadata={calculateMetadata}
      />
      <Composition
        id="CodeSlide"
        component={CodeSlide}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ title: "", language: "text", code: "", durationSeconds: 5 } as CodeProps}
        calculateMetadata={calculateMetadata}
      />
    </>
  );
};
