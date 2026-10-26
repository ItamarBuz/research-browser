"""Online-source configuration: what is enabled, and the optional credentials."""

from rb_engine.adapters.sources.common import SourceCredentials
from rb_engine.domain.works import SourceName
from rb_engine.runtime.preferences import OnlineSettings, PreferencesStore
from rb_engine.runtime.secrets import SecretStore

OPENALEX_KEY = "openalex_api_key"
SEMANTIC_SCHOLAR_KEY = "semantic_scholar_api_key"
SECRET_NAMES = (OPENALEX_KEY, SEMANTIC_SCHOLAR_KEY)


class OnlineConfig:
    def __init__(self, preferences: PreferencesStore, secrets: SecretStore) -> None:
        self._preferences = preferences
        self._secrets = secrets
        self._cached: SourceCredentials | None = None

    @property
    def secrets(self) -> SecretStore:
        return self._secrets

    def settings(self) -> OnlineSettings:
        return self._preferences.load().online

    def save(self, settings: OnlineSettings) -> None:
        current = self._preferences.load()
        self._preferences.save(current.model_copy(update={"online": settings}))
        self._cached = None

    def enabled_sources(self) -> set[SourceName]:
        settings = self.settings()
        if not settings.enabled:
            return set()
        return set(SourceName) - set(settings.disabled_sources)

    def has_secret(self, name: str) -> bool:
        return bool(self._secrets.get(name))

    def set_secret(self, name: str, value: str | None) -> None:
        if value:
            self._secrets.set(name, value.strip())
        else:
            self._secrets.delete(name)
        self._cached = None

    def credentials(self) -> SourceCredentials:
        if self._cached is None:
            self._cached = SourceCredentials(
                contact_email=self.settings().contact_email,
                openalex_api_key=self._secrets.get(OPENALEX_KEY),
                semantic_scholar_api_key=self._secrets.get(SEMANTIC_SCHOLAR_KEY),
            )
        return self._cached
