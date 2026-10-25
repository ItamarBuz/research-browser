import pytest

from rb_engine.domain.catalog import ALLOWED_LICENSES, ModelRole
from rb_engine.domain.errors import ModelNotFoundError
from rb_engine.domain.hardware import Tier
from rb_engine.runtime.catalog import (
    CatalogError,
    LockedEntry,
    LockedFile,
    ModelCatalog,
    SpecEntry,
    build_catalog,
    load_bundled_catalog,
)
from tests.fakes import EMBED_FILES, model


def _entry(**overrides: object) -> SpecEntry:
    fields: dict[str, object] = {
        "id": "m",
        "name": "M",
        "role": "embedder",
        "tiers": ["lite"],
        "repo": "org/m",
        "license": "mit",
        "files": ["model.onnx"],
    }
    return SpecEntry.model_validate(fields | overrides)


LOCK = {
    "m": LockedEntry(
        revision="b" * 40, files={"model.onnx": LockedFile(sha256="c" * 64, size_bytes=10)}
    )
}


def test_bundled_catalog_covers_every_tier() -> None:
    catalog = load_bundled_catalog()
    for tier in Tier:
        roles = {m.role for m in catalog.recommended_for(tier)}
        expected = {ModelRole.EMBEDDER, ModelRole.NLI, ModelRole.LLM}
        if tier != Tier.LITE:
            expected.add(ModelRole.RERANKER)
        assert roles == expected, tier


def test_bundled_catalog_is_permissively_licensed() -> None:
    assert all(m.license in ALLOWED_LICENSES for m in load_bundled_catalog().all())


def test_build_pins_files_from_lock() -> None:
    (spec,) = build_catalog([_entry()], LOCK).all()
    assert spec.revision == "b" * 40
    assert spec.size_bytes == 10
    assert (
        spec.download_url(spec.files[0])
        == f"https://huggingface.co/org/m/resolve/{'b' * 40}/model.onnx"
    )


def test_rejects_non_permissive_license() -> None:
    with pytest.raises(CatalogError, match="license"):
        build_catalog([_entry(license="cc-by-nc-4.0")], LOCK)


def test_rejects_unpinned_entry() -> None:
    with pytest.raises(CatalogError, match="not pinned"):
        build_catalog([_entry(id="other")], LOCK)


def test_rejects_lock_missing_a_file() -> None:
    with pytest.raises(CatalogError, match="missing files"):
        build_catalog([_entry(files=["model.onnx", "tokenizer.json"])], LOCK)


def test_rejects_two_models_for_same_role_and_tier() -> None:
    with pytest.raises(CatalogError, match="both"):
        ModelCatalog([model("a", EMBED_FILES), model("b", EMBED_FILES)])


def test_unknown_model_id() -> None:
    with pytest.raises(ModelNotFoundError):
        ModelCatalog([]).get("nope")
