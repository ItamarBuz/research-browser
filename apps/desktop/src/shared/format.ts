const GIGABYTE = 1024 ** 3;
const MEGABYTE = 1024 ** 2;

const FIRST_STRONG_ISOLATE = "⁨";
const POP_DIRECTIONAL_ISOLATE = "⁩";

/**
 * Wraps text in a Unicode first-strong isolate, so a value like "63.7 GB" keeps its own
 * direction inside Hebrew sentences instead of being reordered to "GB 63.7". It works in
 * plain strings, which matters because these values are interpolated into translations.
 */
export function isolate(text: string): string {
  return `${FIRST_STRONG_ISOLATE}${text}${POP_DIRECTIONAL_ISOLATE}`;
}

/** Localized byte size, e.g. "2.4 GB", with MB below one gigabyte. */
export function formatBytes(bytes: number, language: string): string {
  const [value, unit] =
    bytes >= GIGABYTE ? [bytes / GIGABYTE, "gigabyte"] : [bytes / MEGABYTE, "megabyte"];
  const text = new Intl.NumberFormat(language, {
    style: "unit",
    unit,
    unitDisplay: "short",
    maximumFractionDigits: value >= 100 ? 0 : 1,
  }).format(value);
  return isolate(text);
}

export function formatGigabytes(gigabytes: number, language: string): string {
  return formatBytes(gigabytes * GIGABYTE, language);
}

export function formatPercent(fraction: number, language: string): string {
  return isolate(
    new Intl.NumberFormat(language, { style: "percent", maximumFractionDigits: 0 }).format(
      fraction,
    ),
  );
}
