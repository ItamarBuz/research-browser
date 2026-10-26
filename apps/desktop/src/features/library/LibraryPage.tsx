import { useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";

import { useEngine } from "../../shared/api/EngineContext";
import type { ImportResult, IndexStatus, LibraryDocument } from "../../shared/api/engine";
import type { View } from "../../shared/navigation";
import { useLibrary } from "./useLibrary";

const isPdf = (file: File) =>
  file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function StatusLabel({ document }: { document: LibraryDocument }) {
  const { t } = useTranslation();
  switch (document.status) {
    case "queued":
    case "parsing":
    case "indexing":
      return <span className="badge badge--pending">{t(`library.status.${document.status}`)}</span>;
    case "failed":
      return (
        <span className="error">
          {t("library.status.failed")}: {document.error}
        </span>
      );
    case "ready":
      return document.searchable ? (
        <span className="badge badge--ok">{t("library.status.searchable")}</span>
      ) : (
        <span className="badge" title={document.error ?? undefined}>
          {t("library.status.notIndexed")}
        </span>
      );
  }
}

function IndexBanner({
  index,
  onIndex,
  onNavigate,
}: {
  index: IndexStatus;
  onIndex: () => void;
  onNavigate: (view: View) => void;
}) {
  const { t } = useTranslation();
  if (index.busy) {
    return (
      <p className="status status--pending" role="status">
        {t("library.banner.busy")}
      </p>
    );
  }
  if (index.pending_documents === 0) return null;
  const count = index.pending_documents;
  return (
    <div className="banner" role="status">
      {index.model_ready ? (
        <>
          <span>{t("library.banner.pending", { count })}</span>
          <button type="button" className="primary" onClick={onIndex}>
            {t("library.banner.indexNow")}
          </button>
        </>
      ) : (
        <>
          <span>{t("library.banner.modelMissing", { count })}</span>
          <button
            type="button"
            onClick={() => {
              onNavigate("settings");
            }}
          >
            {t("library.banner.downloadModel")}
          </button>
        </>
      )}
    </div>
  );
}

function DocumentRow({
  document,
  onDelete,
}: {
  document: LibraryDocument;
  onDelete: (id: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [confirming, setConfirming] = useState(false);
  const { metadata } = document;
  return (
    <tr>
      <th scope="row">
        <span className="doc-title" dir="auto">
          {metadata.title}
        </span>
        <span className="muted doc-file" dir="auto">
          {document.file_name}
        </span>
      </th>
      <td>{document.language ? t(`languages.${document.language}`) : "—"}</td>
      <td>{document.page_count || "—"}</td>
      <td>
        <StatusLabel document={document} />
      </td>
      <td>
        {confirming ? (
          <span className="row-actions">
            <button type="button" className="danger" onClick={() => void onDelete(document.id)}>
              {t("library.confirmDelete")}
            </button>
            <button
              type="button"
              onClick={() => {
                setConfirming(false);
              }}
            >
              {t("library.cancel")}
            </button>
          </span>
        ) : (
          <button
            type="button"
            aria-label={`${t("library.delete")}: ${metadata.title}`}
            onClick={() => {
              setConfirming(true);
            }}
          >
            {t("library.delete")}
          </button>
        )}
      </td>
    </tr>
  );
}

export function LibraryPage({
  onNavigate,
  pollMs,
}: {
  onNavigate: (view: View) => void;
  pollMs?: number;
}) {
  const { t } = useTranslation();
  const api = useEngine();
  const library = useLibrary(pollMs);
  const [uploading, setUploading] = useState(false);
  const [rejected, setRejected] = useState<ImportResult[]>([]);
  const [actionError, setActionError] = useState<string>();
  const [dragging, setDragging] = useState(false);

  async function run(action: () => Promise<void>) {
    setActionError(undefined);
    try {
      await action();
    } catch (error) {
      setActionError(messageOf(error));
    }
  }

  const importFiles = (files: File[]) =>
    run(async () => {
      const pdfs = files.filter(isPdf);
      if (pdfs.length === 0) return;
      setUploading(true);
      try {
        const results = await api.importDocuments(pdfs);
        setRejected(results.filter((r) => r.error));
        await library.reload();
      } finally {
        setUploading(false);
      }
    });

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    void importFiles(Array.from(event.dataTransfer.files));
  }

  const error = library.error ?? actionError;
  const documents = library.data?.documents ?? [];

  return (
    <div className="library">
      <h1 className="page-title">{t("library.title")}</h1>

      <label
        className={`dropzone${dragging ? " dropzone--active" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => {
          setDragging(false);
        }}
        onDrop={onDrop}
      >
        <input
          type="file"
          accept="application/pdf,.pdf"
          multiple
          className="visually-hidden"
          disabled={uploading}
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            event.target.value = ""; // allow choosing the same file again
            void importFiles(files);
          }}
        />
        <strong>{uploading ? t("library.uploading") : t("library.dropzone")}</strong>
        <span className="muted">{t("library.dropzoneHint")}</span>
      </label>

      {rejected.map((r) => (
        <p key={r.file_name} className="error" role="alert">
          {t("library.importFailed", { file: r.file_name, error: r.error })}
        </p>
      ))}
      {error && (
        <p className="status status--error" role="alert">
          {t("library.error", { message: error })}
        </p>
      )}

      {library.data && (
        <IndexBanner
          index={library.data.index}
          onNavigate={onNavigate}
          onIndex={() =>
            void run(async () => {
              await api.reindexLibrary();
              await library.reload();
            })
          }
        />
      )}

      {library.data &&
        (documents.length === 0 ? (
          <p className="muted">{t("library.empty")}</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">{t("library.columns.document")}</th>
                <th scope="col">{t("library.columns.language")}</th>
                <th scope="col">{t("library.columns.pages")}</th>
                <th scope="col">{t("library.columns.status")}</th>
                <th scope="col">{t("library.columns.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((document) => (
                <DocumentRow
                  key={document.id}
                  document={document}
                  onDelete={(id) =>
                    run(async () => {
                      await api.deleteDocument(id);
                      await library.reload();
                    })
                  }
                />
              ))}
            </tbody>
          </table>
        ))}
    </div>
  );
}
