"""Versioned prompts stored as files, with content digests and a lock file."""
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .template import Prompt, PromptTemplate

_VERSION = re.compile(r"v(\d+)")


class RegistryError(LookupError):
    pass


def _digest(system: str, user: str, untrusted) -> str:
    """12-character fingerprint of everything that changes what the model sees."""
    payload = json.dumps({"system": system, "user": user, "untrusted": sorted(untrusted)}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class PromptVersion:
    name: str
    version: str
    digest: str
    template: PromptTemplate
    changelog: str = ""

    @property
    def prompt_id(self) -> str:
        """Store this with every model call: 'summarize_conversation@v2#3f9a1c07be52'."""
        return f"{self.name}@{self.version}#{self.digest}"

    def render(self, values: dict) -> Prompt:
        return self.template.render(values, prompt_id=self.prompt_id)


class PromptRegistry:
    """Loads prompt_library/<name>/<version>.json files.

    active pins a version per prompt, for example {"summarize_conversation": "v2"}.
    Prompts that are not pinned use their highest version.
    """

    def __init__(self, root, active: dict = None):
        self.root = Path(root)
        self.active = dict(active or {})
        self._items = {}
        self._load()

    def _load(self):
        for path in sorted(self.root.glob("*/v*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            name, version = path.parent.name, path.stem
            if data.get("name") != name or data.get("version") != version or not _VERSION.fullmatch(version):
                raise RegistryError(f"{path}: name/version fields must match the folder and file name")
            template = PromptTemplate(
                name=name,
                system=data["system"],
                user=data.get("user", ""),
                untrusted=frozenset(data.get("untrusted", [])),
            )
            self._items[(name, version)] = PromptVersion(
                name, version, _digest(template.system, template.user, template.untrusted),
                template, data.get("changelog", ""),
            )

    def names(self) -> list:
        return sorted({name for name, _ in self._items})

    def versions(self, name: str) -> list:
        found = [v for (n, v) in self._items if n == name]
        return sorted(found, key=lambda v: int(_VERSION.fullmatch(v).group(1)))

    def get(self, name: str, version: str = None) -> PromptVersion:
        version = version or self.active.get(name) or (self.versions(name) or [None])[-1]
        try:
            return self._items[(name, version)]
        except KeyError:
            raise RegistryError(f"Unknown prompt {name}@{version}") from None

    # ---- the lock file: released versions must never change -------------------------

    def lock_data(self) -> dict:
        return {f"{n}@{v}": item.digest for (n, v), item in sorted(self._items.items())}

    def write_lock(self):
        """Record digests of versions that are not in the lock file yet. Never overwrites."""
        path = self.root / "LOCK.json"
        locked = json.loads(path.read_text()) if path.exists() else {}
        for key, digest in self.lock_data().items():
            locked.setdefault(key, digest)
        path.write_text(json.dumps(locked, indent=2, sort_keys=True) + "\n")

    def verify_lock(self) -> list:
        """Return problems: an edited released version, a deleted one, or an unlocked new one."""
        path = self.root / "LOCK.json"
        locked = json.loads(path.read_text()) if path.exists() else {}
        current = self.lock_data()
        problems = []
        for key, digest in locked.items():
            if key not in current:
                problems.append(f"{key}: released version was deleted")
            elif current[key] != digest:
                problems.append(f"{key}: released version was edited (create a new version instead)")
        for key in current:
            if key not in locked:
                problems.append(f"{key}: new version is not in LOCK.json yet (run: python -m prompts.cli lock)")
        return problems
