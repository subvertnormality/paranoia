"""Beta phase-based structural model routing for tracked staged reviews.

One resolver shared by `critique_branch` and `critique_plan`. Handlers keep their
call-level model for claim roles, one-shot review, rebut and query; only staged
structural roles select a model here, and only after the authoritative phase is known.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .config import resolve

BETA_RELEASE = "tiered-review-beta-1"
POLICIES = ("tiered", "strongest")
DEFAULT_POLICY = "tiered"
EFFORTS = ("low", "medium", "high")
BETA_NOTICE = (
    f"BETA ({BETA_RELEASE}): tracked reviews route census/final to the strongest model and "
    "targeted correction to Sol/Opus 5.5, require a cold final before NOT-BLOCKED, and "
    "request unapplied repair proposals after blocked census/final by default."
)


@dataclass(frozen=True)
class PhaseModel:
    phase: str
    tier: str
    model: str
    effort: str
    source: str
    effort_source: str = "release-default"


@dataclass(frozen=True)
class StructuralRouting:
    engine_name: str
    strongest_model: str
    correction_model: str
    policy: str
    policy_source: str
    model_override: str | None
    model_source: str | None
    effort_override: str | None
    effort_source: str | None
    #: Per model-family effort overrides: family -> (effort, source).
    family_efforts: Mapping[str, tuple[str, str]]

    @classmethod
    def resolve(
        cls, engine: Any, arguments: Mapping[str, Any], cfg: Mapping[str, Any],
    ) -> StructuralRouting:
        policy_arg = arguments.get("review_model_policy")
        policy = resolve("review_model_policy", policy_arg, dict(cfg), DEFAULT_POLICY)
        if policy not in POLICIES:
            raise ValueError(
                f"review_model_policy must be one of {list(POLICIES)}, got {policy!r}"
            )
        strongest = engine.default_model
        return cls(
            engine.name, strongest,
            getattr(engine, "correction_model", None) or strongest,
            policy, _source("review_model_policy", policy_arg, cfg),
            resolve("model", arguments.get("model"), dict(cfg), None),
            _source("model", arguments.get("model"), cfg),
            resolve("effort", arguments.get("effort"), dict(cfg), None),
            _source("effort", arguments.get("effort"), cfg),
            _family_efforts(arguments.get("effort_by_model"), cfg.get("effort_by_model")),
        )

    @classmethod
    def pinned(cls, engine_name: str, model: str, effort: str) -> StructuralRouting:
        """Legacy direct callers: one caller-chosen model and effort for every phase."""
        return cls(
            engine_name, model, model, "strongest", "caller-pinned",
            None, None, effort, "caller-pinned", {},
        )

    @property
    def custom(self) -> bool:
        """Whether the cold final departs from the release model or effort.

        Beta qualification is a property of the strongest-model final; an override that
        only changes correction effort (for example `effort_by_model: {sol: high}`)
        leaves it qualified.
        """
        from .engines import default_effort

        if self.model_override is not None:
            return True
        final = self.select("final")
        return final.effort != default_effort(final.model, fallback="high")

    def select(self, phase: str) -> PhaseModel:
        """Pick the structural model for an authoritatively selected phase."""
        from .engines import default_effort, model_family

        tier = "correction" if phase == "correction" and self.policy == "tiered" else "strongest"
        if self.model_override is not None:
            model, source = self.model_override, f"custom-override/{self.model_source}"
        else:
            model = self.correction_model if tier == "correction" else self.strongest_model
            source = f"policy/{self.policy}"
        family = model_family(model)
        if family is not None and family in self.family_efforts:
            effort, origin = self.family_efforts[family]
            effort_source = f"effort-by-model/{family}/{origin}"
        elif self.effort_override is not None:
            effort, effort_source = self.effort_override, f"effort/{self.effort_source}"
        else:
            effort, effort_source = default_effort(model, fallback="high"), "release-default"
        return PhaseModel(phase, tier, model, effort, source, effort_source)

    def acceptance(self, *, snapshot: str, phase_model: PhaseModel) -> dict[str, Any]:
        """The closed durable record written when a cold final settles clear."""
        return {
            "version": 1, "release": BETA_RELEASE, "engine": self.engine_name,
            "model": phase_model.model, "effort": phase_model.effort,
            "policy": self.policy, "custom_override": self.custom,
            "snapshot_digest": snapshot,
        }

    def trailer(self, phase_model: PhaseModel | None) -> str:
        """One inert trailer line; every rendered value passes `routing_value`."""
        from .review_census import routing_value as v

        parts = [f"REVIEW-ROUTING: beta={v(BETA_RELEASE)}", f"policy={v(self.policy)}",
                 f"policy-source={v(self.policy_source)}"]
        if phase_model is not None:
            parts.extend([
                f"phase={v(phase_model.phase)}", f"tier={v(phase_model.tier)}",
                f"model={v(phase_model.model)}", f"effort={v(phase_model.effort)}",
                f"model-source={v(phase_model.source)}",
                f"effort-source={v(phase_model.effort_source)}",
            ])
        if self.family_efforts:
            parts.append("effort-by-model=" + ",".join(
                f"{v(family)}/{v(effort)}({v(source)})"
                for family, (effort, source) in sorted(self.family_efforts.items())
            ))
        if self.custom:
            parts.append("custom-override=yes (not beta-qualified)")
        return " ".join(parts)


def _family_efforts(explicit: Any, configured: Any) -> dict[str, tuple[str, str]]:
    """Merge per model-family efforts key by key: argument, then repository config."""
    from .engines import MODEL_FAMILY_EFFORT

    merged: dict[str, tuple[str, str]] = {}
    for value, source in ((configured, "repository-config"), (explicit, "argument")):
        if value is None:
            continue
        if not isinstance(value, Mapping):
            raise ValueError("effort_by_model must map model families to efforts")
        for family, effort in value.items():
            if family not in MODEL_FAMILY_EFFORT:
                raise ValueError(
                    f"effort_by_model key {family!r} is not one of "
                    f"{sorted(MODEL_FAMILY_EFFORT)}"
                )
            if effort not in EFFORTS:
                raise ValueError(
                    f"effort_by_model[{family!r}] must be one of {list(EFFORTS)}"
                )
            merged[family] = (effort, source)
    return merged


def _source(key: str, explicit: Any, cfg: Mapping[str, Any]) -> str:
    if explicit is not None:
        return "argument"
    if key in cfg and cfg[key] is not None:
        return "repository-config"
    return "release-default"


def proposal_mode(arguments: Mapping[str, Any]) -> str:
    """Preserve request origin: omitted is automatic, never coerced to a boolean."""
    value = arguments.get("propose_patch")
    if value is None:
        return "auto"
    if value is True:
        return "explicit"
    if value is False:
        return "off"
    raise ValueError("propose_patch must be a boolean when supplied")
