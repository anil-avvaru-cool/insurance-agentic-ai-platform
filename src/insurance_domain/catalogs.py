"""Versioned local customer content and routing catalogs, loaded at startup."""
import json
from datetime import date
from pathlib import Path
from insurance_domain.intake import DomainError


class Catalogs:
    def __init__(self, path):
        self.data = json.loads(Path(path).read_text())
        if not self.data["version"] or self.data["production_approved"] is not False:
            raise ValueError("Invalid local catalog")
        self.teams = self.data["teams"]
        if not self.teams or any(t not in self.teams for t in self.data["routing"].values()):
            raise ValueError("Invalid team catalog")
        ids = [s["id"] for s in self.data["sources"]]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate source")
        for s in self.data["sources"]:
            date.fromisoformat(s["effective_from"])
            date.fromisoformat(s["effective_until"])

    def sources(self):
        today = date.today().isoformat()
        return [s for s in self.data["sources"] if s["approved"] and s["audience"] == "customer"
                and s["line"] == "auto" and s["effective_from"] <= today <= s["effective_until"]]

    def answer(self, source_ref):
        matches = [s for s in self.sources() if s["id"] == source_ref]
        if len(matches) != 1:
            raise DomainError("unsupported_source")
        s = matches[0]
        return {"message": s["text"], "source_ref": s["id"], "source_version": s["version"],
                "catalog_version": self.data["version"], "synthetic": True}

    def team(self, priority):
        return self.data["routing"]["urgent" if priority == "urgent" else "routine"]
