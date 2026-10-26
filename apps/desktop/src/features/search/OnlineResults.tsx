import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useEngine } from "../../shared/api/EngineContext";
import type { DiscoveryResponse, SourceStatus, WorkHit } from "../../shared/api/engine";
import type { View } from "../../shared/navigation";
import { openExternal } from "../../shared/openExternal";

const MAX_AUTHORS = 3;

type AddState =
  { kind: "idle" } | { kind: "adding" } | { kind: "added" } | { kind: "failed"; message: string };

function SourceChip({ status }: { status: SourceStatus }) {
  const { t } = useTranslation();
  const name = t(`online.sources.${status.source}.name`);
  if (!status.ok) {
    return (
      <span className="chip chip--error" title={status.error ?? undefined}>
        {name}: {t("online.status.failed")}
      </span>
    );
  }
  return (
    <span className="chip chip--ok">
      {name}: {status.count}
      {status.from_cache ? ` · ${t("online.status.cached")}` : ""}
    </span>
  );
}

function WorkCard({ hit }: { hit: WorkHit }) {
  const { t } = useTranslation();
  const api = useEngine();
  const { work } = hit;
  const [expanded, setExpanded] = useState(false);
  const [add, setAdd] = useState<AddState>(hit.in_library ? { kind: "added" } : { kind: "idle" });
  const authors = work.authors ?? [];
  const authorText =
    authors.length > MAX_AUTHORS
      ? t("search.authorsMore", { first: authors.slice(0, MAX_AUTHORS).join(", ") })
      : authors.join(", ");

  async function addToLibrary() {
    if (!work.pdf_url) return;
    setAdd({ kind: "adding" });
    try {
      const result = await api.importDocumentFromUrl(work.pdf_url, {
        title: work.title,
        authors,
        year: work.year ?? null,
        doi: work.ids.doi ?? null,
        from_catalog: true,
      });
      setAdd(result.error ? { kind: "failed", message: result.error } : { kind: "added" });
    } catch (error) {
      setAdd({ kind: "failed", message: error instanceof Error ? error.message : String(error) });
    }
  }

  return (
    <li className="result-card">
      <h3 className="result-title" dir="auto">
        {work.title}
      </h3>
      <p className="result-meta muted">
        {authorText && <span dir="auto">{authorText}</span>}
        {work.year != null && <span>{work.year}</span>}
        {work.venue && <span dir="auto">{work.venue}</span>}
        {work.citation_count != null && (
          <span>{t("online.citations", { count: work.citation_count })}</span>
        )}
        {work.language && <span className="badge">{t(`languages.${work.language}`)}</span>}
        {work.sources.map((source) => (
          <span key={source} className="badge">
            {t(`online.sources.${source}.name`)}
          </span>
        ))}
      </p>
      {work.abstract && (
        <p dir="auto" className={expanded ? "abstract" : "abstract abstract--clamped"}>
          {work.abstract}
        </p>
      )}
      <div className="row-actions">
        {work.abstract && (
          <button
            type="button"
            onClick={() => {
              setExpanded(!expanded);
            }}
          >
            {expanded ? t("online.showLess") : t("online.showMore")}
          </button>
        )}
        {work.landing_url && (
          <button type="button" onClick={() => void openExternal(work.landing_url ?? "")}>
            {t("online.open")}
          </button>
        )}
        {add.kind === "added" ? (
          <span className="badge badge--ok">{t("online.inLibrary")}</span>
        ) : work.pdf_url ? (
          <button
            type="button"
            className="primary"
            disabled={add.kind === "adding"}
            onClick={() => void addToLibrary()}
          >
            {add.kind === "adding" ? t("online.adding") : t("online.addToLibrary")}
          </button>
        ) : (
          <span className="muted">{t("online.noFreePdf")}</span>
        )}
      </div>
      {add.kind === "failed" && (
        <p className="error" role="alert">
          {add.message}
        </p>
      )}
    </li>
  );
}

export function OnlineResults({
  response,
  onNavigate,
}: {
  response: DiscoveryResponse;
  onNavigate: (view: View) => void;
}) {
  const { t } = useTranslation();
  const translated = response.query_language === "he" ? response.queries.en : response.queries.he;
  return (
    <section aria-label={t("online.title")} className="online-results">
      <h2>{t("online.title")}</h2>
      <p className="chips">
        {response.sources.map((status) => (
          <SourceChip key={status.source} status={status} />
        ))}
      </p>
      {translated && (
        <p className="muted">
          {t("online.translatedAs")} <bdi>«{translated}»</bdi>
        </p>
      )}
      {response.translation_missing && (
        <div className="banner" role="status">
          <span>{t("online.translationMissing")}</span>
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
      {response.results.length === 0 ? (
        <p className="muted">{t("online.noResults")}</p>
      ) : (
        <ol className="results">
          {response.results.map((hit) => (
            <WorkCard key={hit.work.ids.doi ?? hit.work.title} hit={hit} />
          ))}
        </ol>
      )}
    </section>
  );
}
