import { useState } from "react";
import { useTranslation } from "react-i18next";

import { EngineGate } from "./features/health/EngineGate";
import type { ConnectFn } from "./features/health/useEngineHealth";
import { HomePage } from "./features/home/HomePage";
import { SettingsPage } from "./features/settings/SettingsPage";

type View = "home" | "settings";
const VIEWS: readonly View[] = ["home", "settings"];

interface AppProps {
  connect?: ConnectFn;
  pollMs?: number;
}

export function App({ connect, pollMs }: AppProps) {
  const { t, i18n } = useTranslation();
  const [view, setView] = useState<View>("home");
  const nextLanguage = i18n.language === "he" ? "en" : "he";

  return (
    <div className="app">
      <header className="app__header">
        <span className="app__title">{t("app.title")}</span>
        <nav aria-label={t("nav.label")}>
          {VIEWS.map((v) => (
            <button
              key={v}
              type="button"
              className="nav-link"
              aria-current={view === v ? "page" : undefined}
              onClick={() => {
                setView(v);
              }}
            >
              {t(`nav.${v}`)}
            </button>
          ))}
        </nav>
        <button
          type="button"
          lang={nextLanguage}
          onClick={() => void i18n.changeLanguage(nextLanguage)}
        >
          {t("app.languageToggle")}
        </button>
      </header>
      <main className="app__main">
        <EngineGate {...(connect ? { connect } : {})}>
          {(health) =>
            view === "home" ? (
              <HomePage
                health={health}
                onOpenSettings={() => {
                  setView("settings");
                }}
              />
            ) : (
              <SettingsPage {...(pollMs === undefined ? {} : { pollMs })} />
            )
          }
        </EngineGate>
      </main>
    </div>
  );
}
