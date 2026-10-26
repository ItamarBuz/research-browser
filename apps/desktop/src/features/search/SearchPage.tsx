import { useCallback, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { useEngine } from "../../shared/api/EngineContext";
import {
  EngineRequestError,
  type DocumentHit,
  type LanguageFilter,
  type SearchResponse,
} from "../../shared/api/engine";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import type { View } from "../../shared/navigation";

const FILTERS: readonly LanguageFilter[] = ["cross", "en", "he"];
const MAX_AUTHORS = 3;
const RESULT_LIMIT = 20;
const HTTP_SERVICE_UNAVAILABLE = 503;

type SearchState =
  | { kind: "idle" }
  | { kind: "searching" }
  | { kind: "done"; response: SearchResponse }
  | { kind: "modelMissing" }
  | { kind: "failed"; message: string };

function Authors({ authors }: { authors: string[] }) {
  const { t } = useTranslation();
  if (authors.length === 0) return null;
  const text =
    authors.length > MAX_AUTHORS
      ? t("search.authorsMore", { first: authors.slice(0, MAX_AUTHORS).join(", ") })
      : authors.join(", ");
  return <span dir="auto">{text}</span>;
}

function ResultCard({ hit }: { hit: DocumentHit }) {
  const { t } = useTranslation();
  const { document } = hit;
  const { metadata } = document;
  return (
    <li className="result-card">
      <h2 className="result-title" dir="auto">
        {metadata.title}
      </h2>
      <p className="result-meta muted">
        <Authors authors={metadata.authors ?? []} />
        {metadata.year != null && <span>{metadata.year}</span>}
        {document.language && <span className="badge">{t(`languages.${document.language}`)}</span>}
        <span dir="auto">{document.file_name}</span>
      </p>
      {hit.passages.map((passage) => (
        <blockquote key={passage.passage_id} className="passage" dir="auto">
          <p>{passage.text}</p>
          <footer className="muted">{t("search.page", { page: passage.page })}</footer>
        </blockquote>
      ))}
    </li>
  );
}

export function SearchPage({ onNavigate }: { onNavigate: (view: View) => void }) {
  const { t } = useTranslation();
  const api = useEngine();
  const loadLibrary = useCallback(() => api.getLibrary(), [api]);
  const library = useAsyncResource(loadLibrary);
  const [query, setQuery] = useState("");
  const [language, setLanguage] = useState<LanguageFilter>("cross");
  const [state, setState] = useState<SearchState>({ kind: "idle" });

  async function search(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    setState({ kind: "searching" });
    try {
      const response = await api.searchLibrary({
        query: query.trim(),
        language,
        limit: RESULT_LIMIT,
      });
      setState({ kind: "done", response });
    } catch (error) {
      if (error instanceof EngineRequestError && error.status === HTTP_SERVICE_UNAVAILABLE) {
        setState({ kind: "modelMissing" });
      } else {
        setState({
          kind: "failed",
          message: error instanceof Error ? error.message : String(error),
        });
      }
    }
  }

  const index = library.data?.index;
  const empty = library.data?.documents.length === 0;

  return (
    <div className="search">
      <h1 className="page-title">{t("search.title")}</h1>

      <form className="search-form" onSubmit={(event) => void search(event)}>
        <input
          type="search"
          dir="auto"
          aria-label={t("search.placeholder")}
          placeholder={t("search.placeholder")}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
          }}
        />
        <button type="submit" className="primary" disabled={state.kind === "searching"}>
          {state.kind === "searching" ? t("search.searching") : t("search.submit")}
        </button>
        <fieldset className="filter-choice">
          <legend>{t("search.filterLegend")}</legend>
          {FILTERS.map((filter) => (
            <label key={filter}>
              <input
                type="radio"
                name="language"
                value={filter}
                checked={language === filter}
                onChange={() => {
                  setLanguage(filter);
                }}
              />
              {t(`search.filters.${filter}`)}
            </label>
          ))}
        </fieldset>
        {language === "cross" && <p className="muted hint">{t("search.crossHint")}</p>}
      </form>

      {empty && (
        <div className="banner" role="status">
          <span>{t("search.emptyLibrary")}</span>
          <button
            type="button"
            onClick={() => {
              onNavigate("library");
            }}
          >
            {t("search.goToLibrary")}
          </button>
        </div>
      )}
      {index && index.pending_documents > 0 && (
        <div className="banner" role="status">
          <span>{t("search.pending", { count: index.pending_documents })}</span>
          <button
            type="button"
            onClick={() => {
              onNavigate("library");
            }}
          >
            {t("nav.library")}
          </button>
        </div>
      )}

      {state.kind === "modelMissing" && (
        <div className="status status--error" role="alert">
          <p>{t("search.modelMissing")}</p>
          <button
            type="button"
            onClick={() => {
              onNavigate("settings");
            }}
          >
            {t("search.openSettings")}
          </button>
        </div>
      )}
      {state.kind === "failed" && (
        <p className="status status--error" role="alert">
          {t("search.error", { message: state.message })}
        </p>
      )}
      {state.kind === "done" &&
        (state.response.results.length === 0 ? (
          <p className="muted">{t("search.noResults")}</p>
        ) : (
          <section aria-label={t("search.title")}>
            <p className="muted" role="status">
              {t("search.resultCount", {
                count: state.response.results.length,
                ms: state.response.took_ms,
              })}
            </p>
            <ol className="results">
              {state.response.results.map((hit) => (
                <ResultCard key={hit.document.id} hit={hit} />
              ))}
            </ol>
          </section>
        ))}
    </div>
  );
}
