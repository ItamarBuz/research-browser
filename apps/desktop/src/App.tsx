import { useState } from "react";
import { useTranslation } from "react-i18next";

import { EngineGate } from "./features/health/EngineGate";
import type { ConnectFn } from "./features/health/useEngineHealth";
import { LibraryPage } from "./features/library/LibraryPage";
import { SearchPage } from "./features/search/SearchPage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { VIEWS, type View } from "./shared/navigation";

interface AppProps {
  connect?: ConnectFn;
  pollMs?: number;
}

export function App({ connect, pollMs }: AppProps) {
  const { t, i18n } = useTranslation();
  const [view, setView] = useState<View>("search");
  const nextLanguage = i18n.language === "he" ? "en" : "he";
  const poll = pollMs === undefined ? {} : { pollMs };

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
      <EngineGate {...(connect ? { connect } : {})}>
        {(health) => (
          <>
            <main className="app__main">
              {view === "search" && <SearchPage onNavigate={setView} />}
              {view === "library" && <LibraryPage onNavigate={setView} {...poll} />}
              {view === "settings" && <SettingsPage {...poll} />}
            </main>
            <footer className="app__footer muted" role="status">
              {t("engine.ready")} {/* <bdi> keeps the Latin version intact inside Hebrew */}
              <bdi>v{health.version}</bdi>
            </footer>
          </>
        )}
      </EngineGate>
    </div>
  );
}
