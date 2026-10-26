export const VIEWS = ["search", "library", "settings"] as const;
export type View = (typeof VIEWS)[number];
