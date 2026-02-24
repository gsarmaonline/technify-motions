import React from "react";
import { Composition } from "remotion";
import { FlowchartAnimation, type GraphProps } from "./FlowchartAnimation";

const DEFAULT_PROPS: GraphProps = {
  nodes: [],
  edges: [],
  title: "",
  durationSeconds: 5,
};

export const Root: React.FC = () => {
  return (
    <Composition
      id="FlowchartAnimation"
      component={FlowchartAnimation}
      durationInFrames={150}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={DEFAULT_PROPS}
      calculateMetadata={({ props }) => ({
        durationInFrames: Math.max(90, Math.round((props.durationSeconds ?? 5) * 30)),
      })}
    />
  );
};
