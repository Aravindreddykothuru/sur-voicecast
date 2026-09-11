/**
 * Emotion color is assigned by INDEX, never by matching a label string in
 * code. The backend's emotion model can be swapped for one with different
 * labels (or a different count) at any time; keying color off the label
 * name is how a renamed label would silently lose its color or collide with
 * another. The palette below is the dark studio's four accent hues, in
 * order; anything past the fourth wraps.
 */
const EMO_PALETTE = ["#8898c8", "#34d399", "#f87171", "#818cf8"] as const;

export const emotionColor = (i: number): string => EMO_PALETTE[((i % EMO_PALETTE.length) + EMO_PALETTE.length) % EMO_PALETTE.length];

export const UNCERTAIN_COLOR = "#c084fc";
