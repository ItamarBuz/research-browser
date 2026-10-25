import { useTranslation } from "react-i18next";

import { EngineStatus } from "./features/health/EngineStatus";
import type { ConnectFn } from "./features/health/useEngineHealth";

interface AppProps {
  connect?: ConnectFn;
}

export function App({ connect }: AppProps) {
  const { t, i18n } = useTranslation();
  const nextLanguage = i18n.language === "he" ? "en" : "he";

  return (
    <div className="app">
      <header className="app__header">
        <h1>{t("app.title")}</h1>
        <button
          type="button"
          lang={nextLanguage}
          onClick={() => void i18n.changeLanguage(nextLanguage)}
        >
          {t("app.languageToggle")}
        </button>
      </header>
      <main className="app__main">
        <EngineStatus {...(connect ? { connect } : {})} />
      </main>
    </div>
  );
}
