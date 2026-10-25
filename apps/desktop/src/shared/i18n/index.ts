import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./locales/en.json";
import he from "./locales/he.json";

export const SUPPORTED_LANGUAGES = ["en", "he"] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];

const RTL_LANGUAGES: ReadonlySet<Language> = new Set(["he"]);

export function directionOf(language: Language): "rtl" | "ltr" {
  return RTL_LANGUAGES.has(language) ? "rtl" : "ltr";
}

export function isLanguage(value: string): value is Language {
  return (SUPPORTED_LANGUAGES as readonly string[]).includes(value);
}

/** Keeps <html lang/dir> in sync so the whole layout (CSS logical properties) flips for RTL. */
function applyDocumentLanguage(language: string): void {
  const lang = isLanguage(language) ? language : "en";
  document.documentElement.lang = lang;
  document.documentElement.dir = directionOf(lang);
}

i18n.on("languageChanged", applyDocumentLanguage);

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, he: { translation: he } },
  lng: "en",
  fallbackLng: "en",
  supportedLngs: SUPPORTED_LANGUAGES,
  interpolation: { escapeValue: false }, // React already escapes
});

export default i18n;
