"""Deterministic alert-noise reduction for a batch of observability events."""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple


SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


def reduce_alert_noise(
    alerts: Iterable[Dict[str, Any]],
    cooldown_minutes: int = 15,
    minimum_severity: str = "warning",
) -> Dict[str, Any]:
    """Suppress low-priority alerts and duplicate signatures inside a cooldown."""
    if cooldown_minutes < 0:
        raise ValueError("cooldown_minutes must be zero or greater")
    if minimum_severity not in SEVERITY_RANK:
        raise ValueError("minimum_severity must be info, warning, or critical")

    cooldown_seconds = cooldown_minutes * 60
    grouped: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for alert in alerts:
        signature = (alert["service"], alert["alert_name"], alert["severity"])
        grouped[signature].append(alert)

    actionable: List[Dict[str, Any]] = []
    suppressed: List[Dict[str, Any]] = []
    for signature in sorted(grouped):
        previous_kept_at = None
        for alert in sorted(grouped[signature], key=lambda item: _timestamp(item["timestamp"])):
            observed_at = _timestamp(alert["timestamp"])
            decision = {**alert, "signature": "|".join(signature)}
            if SEVERITY_RANK[alert["severity"]] < SEVERITY_RANK[minimum_severity]:
                decision["suppression_reason"] = "below_minimum_severity"
                suppressed.append(decision)
            elif previous_kept_at and (observed_at - previous_kept_at).total_seconds() < cooldown_seconds:
                decision["suppression_reason"] = "duplicate_within_cooldown"
                suppressed.append(decision)
            else:
                actionable.append(decision)
                previous_kept_at = observed_at

    return {
        "actionable_alerts": actionable,
        "suppressed_alerts": suppressed,
        "summary": {
            "received": len(actionable) + len(suppressed),
            "actionable": len(actionable),
            "suppressed": len(suppressed),
            "reduction_percent": round(100 * len(suppressed) / max(len(actionable) + len(suppressed), 1), 2),
        },
    }


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
