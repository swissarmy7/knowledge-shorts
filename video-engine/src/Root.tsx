import React from "react";
import { Composition, getInputProps } from "remotion";
import { ShortsVideo } from "./ShortsVideo";
import sceneDataImport from "./scene-data.json";

export const RemotionRoot: React.FC = () => {
    // Get props from CLI if available (npx remotion render --props="...")
    const inputProps = getInputProps() || {};

    // Determine the actual scene data. 
    // If inputProps has a 'scenes' array, the CLI passed the whole JSON object.
    // Otherwise, we might have been passed an object wrapping sceneData, or we fallback to import.
    const data = (inputProps.scenes) ? inputProps : ((inputProps as any).sceneData || sceneDataImport);

    const fps = 30;

    // Calculate duration safely
    const totalDurationFrames = (data?.scenes || []).reduce(
        (acc: number, s: any) => acc + Math.ceil((s.durationInSeconds || 5) * fps),
        0
    ) || 30; // Min 1 second

    return (
        <>
            <Composition
                id="ShortsVideo"
                component={ShortsVideo}
                durationInFrames={Math.max(1, totalDurationFrames)}
                fps={fps}
                width={1080}
                height={1920}
                // We pass BOTH via defaultProps to ensure ShortsVideo receives them
                defaultProps={{
                    sceneData: data,
                    ...data // Also spread in case ShortsVideo accepts them at root
                } as any}
            />
        </>
    );
};
