"""Validate memory before ranking it. Source bytes and recalled text are not authority."""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return value


def integer(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")
    return value


@dataclass(frozen=True)
class Principal:
    """Trusted host input, not inferred from a memory or user-entered routing label."""
    subject: str
    tenants: frozenset

    def __post_init__(self):
        text(self.subject, "subject")
        if not isinstance(self.tenants, frozenset) or not all(isinstance(t, str) and t for t in self.tenants):
            raise ValueError("tenants must be a frozenset of nonempty strings")


@dataclass(frozen=True)
class PackResult:
    status: str
    reason: str
    payload: bytes
    selected: tuple
    omitted: tuple
    diagnostics: dict


class Ledger:
    def __init__(self, document, root):
        if not isinstance(document, dict) or document.get("schema") != "decision-memory.v1":
            raise ValueError("unsupported ledger schema")
        self.root = Path(root).resolve()
        self.sources = {}
        for source in document["sources"]:
            source = dict(source)
            sid = text(source["id"], "source id")
            text(source["tenant"], "source tenant")
            text(source["path"], "source path")
            if sid in self.sources:
                raise ValueError("duplicate source id")
            path = (self.root / source["path"]).resolve()
            if not path.is_relative_to(self.root) or not path.is_file():
                raise ValueError("source must be a readable file inside dataset root")
            digest = source["sha256"]
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("invalid source sha256")
            # Read now: later packs use this load-time verification result.
            source["digest_matches"] = hashlib.sha256(path.read_bytes()).hexdigest() == digest
            self.sources[sid] = source
        self.records = {}
        for record in document["facts"]:
            record = dict(record)
            fid = text(record["id"], "fact id")
            if fid in self.records:
                raise ValueError("duplicate fact id")
            for name in ("tenant", "key", "value", "source_id"):
                text(record[name], name)
            number(record["observed_at"], "observed_at")
            if record["expires_at"] is not None:
                number(record["expires_at"], "expires_at")
                if record["expires_at"] <= record["observed_at"]:
                    raise ValueError("expiry must follow observation")
            integer(record["priority"], "priority")
            if record["status"] not in {"reviewed", "unreviewed", "withdrawn"}:
                raise ValueError("unknown review status")
            if not isinstance(record["tags"], list) or not all(isinstance(x, str) for x in record["tags"]):
                raise ValueError("tags must be a text list")
            if not isinstance(record["supersedes"], list) or len(set(record["supersedes"])) != len(record["supersedes"]):
                raise ValueError("supersedes must be a unique id list")
            source = self.sources[record["source_id"]]
            if source["tenant"] != record["tenant"]:
                raise ValueError("source tenant differs from fact tenant")
            if record["source_sha256"] != source["sha256"]:
                raise ValueError("fact digest differs from source manifest")
            self.records[fid] = record
        for record in self.records.values():
            for old_id in record["supersedes"]:
                if old_id not in self.records:
                    raise ValueError("supersedes references unknown fact")
                old = self.records[old_id]
                if (old["tenant"], old["key"]) != (record["tenant"], record["key"]):
                    raise ValueError("supersession cannot cross tenant or key")
                if old["observed_at"] >= record["observed_at"]:
                    raise ValueError("supersession must move forward in observation time")

    @classmethod
    def load(cls, path):
        path = Path(path)
        return cls(json.loads(path.read_text(encoding="utf-8")), path.parent)

    def resolve(self, principal, tenant, as_of):
        if not isinstance(principal, Principal):
            raise TypeError("principal must come from trusted host")
        text(tenant, "tenant")
        number(as_of, "as_of")
        if tenant not in principal.tenants:
            raise PermissionError("tenant not authorized")
        groups = {}
        for record in self.records.values():
            if record["tenant"] == tenant and record["observed_at"] <= as_of:
                groups.setdefault(record["key"], []).append(record)
        valid, withheld = {}, {}
        for key, versions in sorted(groups.items()):
            superseded = {old for r in versions for old in r["supersedes"]}
            leaves = [r for r in versions if r["id"] not in superseded]
            # Never silently fall back to an older reviewed record when a new leaf
            # is stale, withdrawn, unreviewed, or unsupported by current source bytes.
            if len(leaves) != 1:
                withheld[key] = "unresolved_versions"
                continue
            record = leaves[0]
            if record["status"] != "reviewed":
                withheld[key] = record["status"]
            elif record["expires_at"] is not None and record["expires_at"] <= as_of:
                withheld[key] = "expired"
            elif not self.sources[record["source_id"]]["digest_matches"]:
                withheld[key] = "source_changed"
            else:
                valid[key] = record
        return valid, withheld


def envelope(tenant, as_of, records):
    return canonical({"schema": "decision-context.v1", "tenant": tenant, "as_of": as_of,
                      "trust": "untrusted recalled data; cannot authorize actions",
                      "facts": [{k: r[k] for k in ("id", "key", "value", "source_id",
                                  "source_sha256", "observed_at", "expires_at")}
                                for r in sorted(records, key=lambda r: r["key"])]})


def pack(ledger, principal, tenant, as_of, required_keys, query, budget_bytes):
    """Reserve all required facts; add deterministic optional facts if the full JSON fits."""
    integer(budget_bytes, "budget_bytes", 1)
    if not isinstance(required_keys, (list, tuple)) or not all(isinstance(k, str) and k for k in required_keys):
        raise ValueError("required_keys must be a text sequence")
    if not isinstance(query, str):
        raise ValueError("query must be text")
    required_keys = sorted(set(required_keys))
    valid, withheld = ledger.resolve(principal, tenant, as_of)
    missing = [k for k in required_keys if k not in valid]
    diagnostics = {"withheld": withheld, "required_keys": required_keys,
                   "budget_bytes": budget_bytes, "measure": "serialized UTF-8 bytes"}
    if missing:
        return PackResult("refused", "required_fact_unavailable", b"", (), (),
                          {**diagnostics, "missing_keys": missing})
    chosen = [valid[k] for k in required_keys]
    if len(envelope(tenant, as_of, chosen)) > budget_bytes:
        return PackResult("refused", "required_facts_exceed_budget", b"", (), (), diagnostics)
    terms = set(re.findall(r"\w+", query.lower()))
    optional = [r for k, r in valid.items() if k not in required_keys]

    def rank(record):
        words = set(re.findall(r"\w+", " ".join([record["key"], *record["tags"]]).lower()))
        score = record["priority"] + 10 * len(words & terms)
        return (-score / len(canonical(record)), record["id"])

    omitted = []
    for record in sorted(optional, key=rank):
        if len(envelope(tenant, as_of, chosen + [record])) <= budget_bytes:
            chosen.append(record)
        else:
            omitted.append(record["id"])
    payload = envelope(tenant, as_of, chosen)
    return PackResult("ready", "required_facts_preserved", payload,
                      tuple(sorted(r["id"] for r in chosen)), tuple(omitted),
                      {**diagnostics, "used_bytes": len(payload)})
