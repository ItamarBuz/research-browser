from pathlib import Path

from rb_engine.domain.hardware import Tier
from rb_engine.runtime.preferences import PreferencesStore, UserPreferences


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert PreferencesStore(tmp_path / "prefs.json").load() == UserPreferences()


def test_round_trip(tmp_path: Path) -> None:
    store = PreferencesStore(tmp_path / "nested" / "prefs.json")
    store.save(UserPreferences(tier_override=Tier.PRO))
    assert store.load().tier_override == Tier.PRO
    assert list((tmp_path / "nested").iterdir()) == [tmp_path / "nested" / "prefs.json"]


def test_corrupt_file_falls_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "prefs.json"
    path.write_text("{not json", encoding="utf-8")
    assert PreferencesStore(path).load() == UserPreferences()


def test_unknown_keys_from_newer_versions_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "prefs.json"
    path.write_text('{"tier_override": "lite", "future_setting": 1}', encoding="utf-8")
    assert PreferencesStore(path).load().tier_override == Tier.LITE
