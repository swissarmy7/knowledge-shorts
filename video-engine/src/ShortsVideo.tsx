import React from "react";
import {
    AbsoluteFill,
    Audio,
    Img,
    Video,
    Sequence,
    interpolate,
    spring,
    useCurrentFrame,
    useVideoConfig,
    staticFile,
} from "remotion";

// Scene data types
interface Overlay {
    type: "text" | "image";
    content: string;
    position: string;
    startTime: number;
    duration?: number;
}

interface Scene {
    sceneId: number;
    imagePath: string;
    videoPath?: string;
    audioPath: string;
    script: string;
    durationInSeconds: number;
    motion: string;
    characterId: string;
    volume?: number;
    overlays?: Overlay[];
}

interface CharacterMetadata {
    id: string;
    name: string;
    description: string;
    voice_category: string;
    color: string;
}

export type VideoTitle = string | { highlight: string; rest: string };

interface SceneData {
    videoTitle: VideoTitle;
    subject?: string;
    situationSetting?: {
        time_period: string;
        situation: string;
        concept: string;
    };
    characters: CharacterMetadata[];
    scenes: Scene[];
    fullNarrationPath?: string;
}

interface ShortsVideoProps {
    sceneData?: SceneData;
    scenes?: Scene[];
    videoTitle?: VideoTitle;
    characters?: CharacterMetadata[];
}

// Map for temporary character info during render
const GET_CHAR_INFO = (charId: string, characters: CharacterMetadata[] = []) => {
    const char = characters.find(c => c.id === charId);
    return char || { name: "???", color: "#ffffff" };
};

// Persistent Header Overlay (Top-Center, Always Visible)
const HEADER_HEIGHT = 360;

const PersistentHeader: React.FC<{ title: VideoTitle }> = ({ title }) => {
    if (!title) return null;

    let highlight = "";
    let rest = "";

    if (typeof title === "string") {
        const titleParts = title.split(' ');
        highlight = titleParts[0] || "";
        rest = titleParts.slice(1).join(' ');
    } else {
        highlight = title.highlight || "";
        rest = title.rest || "";
    }

    return (
        <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: HEADER_HEIGHT,
            backgroundColor: '#000',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'flex-end',
            alignItems: 'center',
            zIndex: 150,
            padding: '0 40px 40px 40px',
            textAlign: 'center'
        }}>
            {/* Top Line (Yellow) */}
            <div style={{
                fontSize: 68,
                fontWeight: 900,
                color: '#d4ff00',
                fontFamily: "'Noto Sans CJK KR', 'NanumGothic', sans-serif",
                lineHeight: 1.1,
                marginBottom: 8,
                textTransform: 'uppercase' as const,
                letterSpacing: -1
            }}>
                {highlight}
            </div>
            {/* Bottom Line (White) */}
            <div style={{
                fontSize: 48,
                fontWeight: 800,
                color: '#fff',
                fontFamily: "'Noto Sans CJK KR', 'NanumGothic', sans-serif",
                lineHeight: 1.1,
                letterSpacing: -0.5
            }}>
                {rest}
            </div>

            {/* Decorative bottom border for the frame */}
            <div style={{
                position: 'absolute',
                bottom: 0,
                left: 0,
                right: 0,
                height: 4,
                background: 'linear-gradient(90deg, transparent, #d4ff00, transparent)'
            }} />
        </div>
    );
};

// Subject Label (Top-Right, Below Header)
const SubjectLabel: React.FC<{ subject: string }> = ({ subject }) => {
    if (!subject) return null;

    return (
        <div style={{
            position: 'absolute',
            top: HEADER_HEIGHT + 48,
            right: 110,
            zIndex: 160,
        }}>
            <div style={{
                background: 'rgba(212, 255, 0, 0.95)',
                padding: '8px 20px',
                borderRadius: '12px',
                boxShadow: '0 10px 30px rgba(0,0,0,0.4)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
            }}>
                <span style={{
                    color: '#000',
                    fontSize: 34,
                    fontWeight: 900,
                    fontFamily: "'Noto Sans CJK KR', 'NanumGothic', sans-serif",
                }}>
                    {subject}
                </span>
            </div>
        </div>
    );
};

// Main Title Overlay for the start of the video (0-1.5s)
const MainTitle: React.FC<{ title: string }> = ({ title }) => {
    const frame = useCurrentFrame();
    const { fps, width } = useVideoConfig();

    // Entrance animation: Pop in
    const pop = spring({
        fps,
        frame,
        config: { damping: 12, stiffness: 120, mass: 0.6 },
    });

    // Exit animation: Fade out during the last 15 frames
    const duration = 90; // 3.0s (30fps)
    const fadeOut = interpolate(
        frame,
        [duration - 15, duration],
        [1, 0],
        { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
    );

    // Subtle slow zoom animation
    const slowZoom = interpolate(frame, [0, duration], [1, 1.05]);

    const scale = interpolate(pop, [0, 1], [0.8, 1]);
    const translateY = interpolate(pop, [0, 1], [100, 0]);
    const opacity = Math.min(pop, fadeOut);

    if (!title) return null;

    return (
        <AbsoluteFill style={{
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 200, // Highest priority
            pointerEvents: 'none'
        }}>
            <div style={{
                transform: `scale(${scale * slowZoom}) translateY(${translateY}px)`,
                opacity,
                width: '92%',
                display: 'flex',
                justifyContent: 'center',
            }}>
                <div style={{
                    background: 'rgba(0, 0, 0, 0.85)',
                    padding: '45px 65px',
                    borderRadius: 35,
                    border: '10px solid #d4ff00', // Neon Yellow/Lime accent
                    boxShadow: '0 40px 100px rgba(0,0,0,0.8), 0 0 30px rgba(212, 255, 0, 0.2)',
                    textAlign: 'center',
                    backdropFilter: 'blur(20px)',
                    position: 'relative',
                }}>
                    {/* Decorative element */}
                    <div style={{
                        position: 'absolute',
                        top: -20,
                        left: '50%',
                        transform: 'translateX(-50%)',
                        background: '#d4ff00',
                        color: '#000',
                        fontSize: 24,
                        fontWeight: 900,
                        padding: '4px 20px',
                        borderRadius: 10,
                        textTransform: 'uppercase',
                        letterSpacing: 2
                    }}>
                        Must Watch
                    </div>
                    <div style={{
                        fontSize: 110, // Increased from 92
                        fontWeight: 900,
                        color: '#fff', // White text on dark glass
                        lineHeight: 1.1,
                        fontFamily: "'Noto Sans CJK KR', 'NanumGothic', sans-serif",
                        wordBreak: 'keep-all',
                        letterSpacing: -3,
                        textShadow: '0 5px 20px rgba(0,0,0,0.5)'
                    }}>
                        {title}
                    </div>
                </div>
            </div>
        </AbsoluteFill>
    );
};

const StyledSubtitle: React.FC<{
    text: string;
    visibleChars: number;
    charInfo: { name: string; color: string };
}> = ({ text, visibleChars, charInfo }) => {
    // Remove action descriptions in parentheses for display
    const cleanText = text.replace(/\([^)]*\)/g, "").trim();
    const visibleText = cleanText.slice(0, visibleChars);

    return (
        <div style={{ textAlign: "left", width: '100%', paddingLeft: 56 }}>
            {/* Main subtitle text (Centered-Left) */}
            <div
                style={{
                    color: "white",
                    fontSize: 54,
                    fontWeight: 900,
                    lineHeight: 1.4,
                    textShadow:
                        "0 4px 12px rgba(0,0,0,0.9), 0 0 40px rgba(0,0,0,0.5)",
                    fontFamily: "'Noto Sans CJK KR', 'NanumGothic', sans-serif",
                    letterSpacing: -1,
                    wordBreak: "keep-all" as const,
                    maxWidth: '78%',
                    borderLeft: '10px solid #d4ff00',
                    paddingLeft: 24,
                }}
            >
                {visibleText}
            </div>
        </div>
    );
};

// Ken Burns effect configurations per motion type
const MOTION_CONFIGS: Record<
    string,
    {
        startScale: number;
        endScale: number;
        startX: number;
        endX: number;
        startY: number;
        endY: number;
    }
> = {
    talking: { startScale: 1.0, endScale: 1.15, startX: 0, endX: 0, startY: 0, endY: -20 },
    pointing: { startScale: 1.1, endScale: 1.0, startX: -30, endX: 30, startY: 0, endY: 0 },
    thinking: { startScale: 1.05, endScale: 1.2, startX: 10, endX: -10, startY: 10, endY: -10 },
    jumping: { startScale: 1.0, endScale: 1.2, startX: 0, endX: 0, startY: 20, endY: -30 },
    surprised: { startScale: 1.3, endScale: 1.0, startX: 0, endX: 0, startY: 0, endY: 0 },
    zoom_in: { startScale: 1.0, endScale: 1.4, startX: 0, endX: 0, startY: 0, endY: -20 },
    zoom_out: { startScale: 1.3, endScale: 1.0, startX: 0, endX: 0, startY: -10, endY: 0 },
    slide: { startScale: 1.05, endScale: 1.05, startX: -50, endX: 50, startY: 0, endY: 0 },
    fade: { startScale: 1.0, endScale: 1.1, startX: 0, endX: 0, startY: 0, endY: 0 },
    bounce: { startScale: 1.0, endScale: 1.15, startX: 0, endX: 0, startY: 10, endY: -20 },
    slow_push: { startScale: 1.02, endScale: 1.14, startX: 0, endX: 0, startY: 0, endY: -16 },
};

const POSITION_STYLES: Record<string, React.CSSProperties> = {
    "top-left": { top: 450, left: 60, alignItems: "flex-start" },
    "top-right": { top: 450, right: 60, alignItems: "flex-end" },
    center: {
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        justifyContent: "center",
        alignItems: "center",
    },
    "bottom-left": { bottom: 500, left: 60, alignItems: "flex-start" },
    "bottom-right": { bottom: 500, right: 60, alignItems: "flex-end" },
};

const MAIN_VISUAL_OVERLAY_STYLE: React.CSSProperties = {
    position: "absolute",
    top: 40,
    left: 40,
    right: 40,
    bottom: 40,
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
};

const ImageOverlay: React.FC<{ overlay: Overlay }> = ({ overlay }) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();

    // Fade in/out logic
    const startFrame = (overlay.startTime || 0) * fps;
    const endFrame = startFrame + (overlay.duration || 4) * fps;

    if (frame < startFrame || (overlay.duration && frame > endFrame)) return null;

    const opacity = interpolate(
        frame,
        [startFrame, startFrame + 10, endFrame - 10, endFrame],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    const posStyle = overlay.position === "blackboard"
        ? MAIN_VISUAL_OVERLAY_STYLE
        : (POSITION_STYLES[overlay.position] || MAIN_VISUAL_OVERLAY_STYLE);

    return (
        <AbsoluteFill
            style={{
                ...posStyle,
                display: "flex",
                pointerEvents: "none",
                opacity,
                zIndex: 100,
            }}
        >
            <Img
                src={overlay.content ? staticFile(overlay.content) : ""}
                style={{
                    width: "100%",
                    height: "100%",
                    objectFit: "contain",
                }}
            />
        </AbsoluteFill>
    );
};

// Single Scene component with Ken Burns + styled subtitle + overlays
const SceneComponent: React.FC<{
    scene: Scene;
    characters: CharacterMetadata[];
    fullNarrationPath?: string;
    isFirstScene: boolean;
    isLastScene: boolean;
}> = ({ scene, characters, fullNarrationPath, isFirstScene, isLastScene }) => {
    const frame = useCurrentFrame();
    const { fps, durationInFrames } = useVideoConfig();
    const charInfo = GET_CHAR_INFO(scene.characterId, characters);

    // Image motion is intentionally disabled here.
    // Scene images may already be converted to per-scene video clips by agy;
    // Remotion should keep the visual layer static and only add the header/subtitles.
    const scale = 1;
    const translateX = 0;
    const translateY = 0;

    // Avoid per-scene black flashes by limiting fades to the video edges only.
    const fadeIn = isFirstScene
        ? interpolate(frame, [0, 6], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
        })
        : 1;

    const fadeOut = isLastScene
        ? interpolate(
            frame,
            [Math.max(0, durationInFrames - 6), durationInFrames],
            [1, 0],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        )
        : 1;

    const opacity = Math.min(fadeIn, fadeOut);

    // Character-by-character reveal for subtitle
    const cleanScript = scene.script.replace(/\([^)]*\)/g, "").trim();
    const totalChars = cleanScript.length;
    const charsPerFrame = totalChars / (durationInFrames * 0.85);
    const visibleChars = Math.min(
        totalChars,
        Math.ceil((frame + 1) * charsPerFrame)
    );

    // Subtitle slide-up entrance
    const subtitleSpring = spring({
        fps,
        frame: frame - 5,
        config: { damping: 15, stiffness: 100 },
    });

    const subtitleY = interpolate(subtitleSpring, [0, 1], [50, 0]);
    const subtitleOpacity = interpolate(subtitleSpring, [0, 1], [0, 1]);

    return (
        <AbsoluteFill style={{ opacity, backgroundColor: "#000" }}>
            {/* Main visual stage */}
            <div
                style={{
                    position: 'absolute',
                    top: HEADER_HEIGHT,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    background: 'linear-gradient(180deg, #0d1117 0%, #050608 100%)',
                }}
            >
                <div
                    style={{
                        position: 'absolute',
                        top: 28,
                        left: 80,
                        right: 80,
                        bottom: 440,
                        borderRadius: 28,
                        boxShadow: '0 24px 64px rgba(0,0,0,0.5)',
                        background: '#0f1720',
                        overflow: 'hidden',
                    }}
                >
                    <div
                        style={{
                            position: 'relative',
                            width: '100%',
                            height: '100%',
                            overflow: "hidden",
                            borderRadius: 28,
                            background:
                                'radial-gradient(circle at 18% 16%, rgba(255,255,255,0.12), transparent 24%), radial-gradient(circle at 82% 12%, rgba(212,255,0,0.08), transparent 20%), #101820',
                            boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.05)',
                        }}
                    >
                        <div style={{
                            width: '100%',
                            height: '100%',
                            transform: `scale(${scale}) translate(${translateX}px, ${translateY}px)`,
                        }}>
                            {scene.videoPath ? (
                                <Video
                                    src={staticFile(scene.videoPath)}
                                    muted
                                    loop
                                    style={{
                                        width: "100%",
                                        height: "100%",
                                        objectFit: "cover",
                                    }}
                                />
                            ) : (
                                <Img
                                    src={scene.imagePath ? staticFile(scene.imagePath) : ""}
                                    style={{
                                        width: "100%",
                                        height: "100%",
                                        objectFit: "cover",
                                    }}
                                />
                            )}
                        </div>

                        <div
                            style={{
                                position: 'absolute',
                                top: 0,
                                left: 0,
                                right: 0,
                                bottom: 0,
                                background:
                                    "linear-gradient(to top, rgba(0,0,0,0.42) 0%, rgba(0,0,0,0.08) 38%, transparent 68%)",
                            }}
                        />
                    </div>
                </div>

                <div
                    style={{
                        position: 'absolute',
                        left: 0,
                        right: 0,
                        bottom: 0,
                        height: 250,
                        background:
                            'linear-gradient(180deg, rgba(5,6,8,0) 0%, rgba(5,6,8,0.7) 22%, rgba(5,6,8,1) 100%)',
                    }}
                />

                {/* Animated Subtitle with character tag + emphasis */}
                <div
                    style={{
                        position: 'absolute',
                        left: 0,
                        right: 0,
                        bottom: 0,
                        justifyContent: "flex-end",
                        alignItems: "flex-start",
                        paddingBottom: 310,
                        paddingLeft: 88,
                        paddingRight: 28,
                        display: 'flex',
                        flexDirection: 'column'
                    }}
                >
                    <div
                        style={{
                            transform: `translateY(${subtitleY}px)`,
                            opacity: subtitleOpacity,
                        }}
                    >
                        <StyledSubtitle
                            text={scene.script}
                            visibleChars={visibleChars}
                            charInfo={charInfo}
                        />
                    </div>
                </div>
            </div>

            {/* Render image overlays inside the main visual area */}
            {scene.overlays
                ?.filter((ov) => ov.type === "image")
                .map((ov, i) => (
                    <div key={i} style={{
                        position: 'absolute',
                        top: HEADER_HEIGHT + 28,
                        left: 80,
                        right: 80,
                        bottom: 440,
                        pointerEvents: 'none'
                    }}>
                        <ImageOverlay overlay={ov} />
                    </div>
                ))}

            {/* Scene Audio - Only play if NOT using full narration */}
            {!fullNarrationPath && scene.audioPath && (
                <Audio
                    src={staticFile(scene.audioPath)}
                    volume={scene.volume ?? 1.0}
                />
            )}
        </AbsoluteFill>
    );
};

// Main Shorts Video component
export const ShortsVideo: React.FC<ShortsVideoProps> = (props) => {
    // Robust data extraction
    const sceneData = props.sceneData || (props as any);

    const { fps, durationInFrames } = useVideoConfig();

    if (!sceneData || !sceneData.scenes) {
        return <AbsoluteFill style={{ backgroundColor: '#000' }} />;
    }

    let currentFrame = 0;

    return (
        <AbsoluteFill style={{ backgroundColor: "#000" }}>
            {/* Whole Video Narration (User uploaded) */}
            {sceneData.fullNarrationPath && (
                <Audio src={staticFile(sceneData.fullNarrationPath)} volume={1.2} />
            )}

            {sceneData.scenes.map((scene: Scene, index: number) => {
                const durationFrames = Math.ceil(scene.durationInSeconds * fps);
                const startFrame = currentFrame;
                currentFrame += durationFrames;

                return (
                    <Sequence
                        key={scene.sceneId}
                        from={startFrame}
                        durationInFrames={durationFrames}
                        name={`Scene ${scene.sceneId}`}
                    >
                        <SceneComponent
                            scene={scene}
                            characters={sceneData.characters}
                            fullNarrationPath={sceneData.fullNarrationPath}
                            isFirstScene={index === 0}
                            isLastScene={index === sceneData.scenes.length - 1}
                        />
                    </Sequence>
                );
            })}

            {/* Persistent overlays must be rendered after scene sequences so they stay above scene fills. */}
            <div style={{ position: 'absolute', inset: 0, zIndex: 1000, pointerEvents: 'none' }}>
                <PersistentHeader title={sceneData.videoTitle} />
                <SubjectLabel subject={sceneData.subject || ""} />
            </div>
        </AbsoluteFill>
    );
};
