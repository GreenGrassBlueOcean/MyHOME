"""Shared-bus topology of the configured gateways (#453).

Read straight from the config entries, not from loaded handlers, so the answers
do not depend on the order in which the gateways were set up.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.const import CONF_MAC, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_BUS_TOPOLOGY,
    CONF_DELEGATED_WHOS,
    CONF_GATEWAY_ROLE,
    CONF_PRIMARY_GATEWAY,
    DOMAIN,
    ROLE_PRIMARY,
    ROLE_SECONDARY,
    ROLE_STANDBY,
    TOPOLOGY_SHARED,
    TOPOLOGY_STANDALONE,
)


@dataclass(frozen=True)
class RecommendedTopology:
    """Optimal shared-bus configuration inferred from hardware capabilities."""

    primary_mac: str
    secondary_mac: str
    role: str  # ROLE_SECONDARY or ROLE_STANDBY
    delegated_whos: set[int]
    rationale: str


def entry_model(entry: Any) -> str | None:
    """The configured model name of a gateway entry."""
    data = getattr(entry, "data", None)
    if isinstance(data, Mapping):
        model = data.get(CONF_NAME)
        if model:
            return str(model)
    options = getattr(entry, "options", None)
    if isinstance(options, Mapping):
        model = options.get(CONF_NAME)
        if model:
            return str(model)
    title = getattr(entry, "title", "") or ""
    if " Gateway" in title:
        return title.split(" Gateway")[0].strip()
    return title or None


def gateway_tier(model: str | None) -> int:
    """Return performance tier for a gateway model (1 = Linux fast, 2 = Modern scenario/Touch, 3 = Legacy)."""
    norm = (model or "").strip().upper()
    if any(k in norm for k in ("F454", "MYHOMESERVER1", "F455", "F461")):
        return 1
    if any(k in norm for k in ("MH201", "MH202", "H4890", "AM4890", "LN4890")):
        return 2
    return 3


def gateway_supported_whos(model: str | None) -> set[int]:
    """Retrieve supported WHO set from OWNd profiles and trace availability matrix."""
    whos: set[int] = set()
    norm = (model or "").strip().upper()
    try:
        from OWNd.profiles import get_gateway_profile

        profile = get_gateway_profile(model or "")
        supported = getattr(profile, "supported_who", None)
        if supported:
            whos.update(int(w) for w in supported if isinstance(w, (int, str)))
    except Exception:
        pass

    # Enrich from hardware trace availability matrix (docs/trace-availability.md):
    if "H4890" in norm or "AM4890" in norm:
        whos.update({1, 2, 4, 5, 9, 16, 18, 22, 25})
    elif "MH200N" in norm:
        whos.update({0, 1, 2, 4, 5, 9, 13, 14, 15, 16, 17, 18, 22, 25})
    elif "MYHOMESERVER1" in norm:
        whos.discard(5)
        whos.discard(22)
    elif "MH202" in norm:
        whos.update({1, 2, 4, 9, 14, 18, 25})
    elif "F454" in norm:
        whos.update({1, 2, 4, 5, 9, 14, 16, 18, 25})

    return {w for w in whos if w in {1, 2, 4, 5, 9, 15, 16, 18, 22, 25}}


def infer_shared_bus_topology(entry_a: Any, entry_b: Any) -> RecommendedTopology:
    """Infer optimal primary/secondary role and delegated WHOs for a gateway pair on a shared bus."""
    mac_a = entry_mac(entry_a) or ""
    mac_b = entry_mac(entry_b) or ""
    model_a = entry_model(entry_a)
    model_b = entry_model(entry_b)

    tier_a = gateway_tier(model_a)
    tier_b = gateway_tier(model_b)
    whos_a = gateway_supported_whos(model_a)
    whos_b = gateway_supported_whos(model_b)

    # Determine Primary vs Follower:
    # 1. Higher tier wins (lower tier number)
    # 2. More supported WHOs wins
    # 3. Deterministic fallback by MAC sort
    if tier_a < tier_b:
        pri_mac, sec_mac = mac_a, mac_b
        pri_whos, sec_whos = whos_a, whos_b
        pri_model, sec_model = model_a or "Gateway A", model_b or "Gateway B"
    elif tier_b < tier_a:
        pri_mac, sec_mac = mac_b, mac_a
        pri_whos, sec_whos = whos_b, whos_a
        pri_model, sec_model = model_b or "Gateway B", model_a or "Gateway A"
    elif len(whos_a) >= len(whos_b):
        pri_mac, sec_mac = mac_a, mac_b
        pri_whos, sec_whos = whos_a, whos_b
        pri_model, sec_model = model_a or "Gateway A", model_b or "Gateway B"
    else:
        pri_mac, sec_mac = mac_b, mac_a
        pri_whos, sec_whos = whos_b, whos_a
        pri_model, sec_model = model_b or "Gateway B", model_a or "Gateway A"

    # Compute capability delta: subsystems supported by secondary that primary lacks
    delta = sec_whos - pri_whos
    # If secondary supports Audio Diffusion (WHO 22) or Audio (WHO 16), keep audio coupled
    if (22 in delta or 16 in delta) and (16 in sec_whos or 22 in sec_whos):
        if 16 in sec_whos:
            delta.add(16)
        if 22 in sec_whos:
            delta.add(22)

    if not delta:
        role = ROLE_STANDBY
        delegated: set[int] = set()
        rationale = (
            f"{pri_model} ({pri_mac}) selected as Primary. "
            f"{sec_model} ({sec_mac}) capabilities are fully covered by Primary; configured as Warm Standby for failover."
        )
    else:
        role = ROLE_SECONDARY
        delegated = delta
        subsystems_str = ", ".join(f"WHO {w}" for w in sorted(delegated))
        rationale = (
            f"{pri_model} ({pri_mac}) selected as Primary. "
            f"{sec_model} ({sec_mac}) delegated unique subsystems: {subsystems_str}."
        )

    return RecommendedTopology(
        primary_mac=pri_mac,
        secondary_mac=sec_mac,
        role=role,
        delegated_whos=delegated,
        rationale=rationale,
    )


def _setting(entry: Any, key: str) -> Any:
    """An entry setting, options first, then data."""
    for source in (getattr(entry, "options", None), getattr(entry, "data", None)):
        if isinstance(source, Mapping) and key in source:
            return source[key]
    return None


def entry_mac(entry: Any) -> str | None:
    """The normalised MAC of a gateway entry."""
    data = getattr(entry, "data", None)
    raw = (data.get(CONF_MAC) if isinstance(data, Mapping) else None) or getattr(entry, "unique_id", None)
    return dr.format_mac(str(raw)) if raw else None


def entry_topology(entry: Any) -> str:
    return str(_setting(entry, CONF_BUS_TOPOLOGY) or TOPOLOGY_STANDALONE)


def entry_role(entry: Any) -> str:
    return str(_setting(entry, CONF_GATEWAY_ROLE) or ROLE_PRIMARY)


def entry_is_follower(entry: Any) -> bool:
    """Secondary or standby on a shared bus."""
    return entry_topology(entry) == TOPOLOGY_SHARED and entry_role(entry) in (ROLE_SECONDARY, ROLE_STANDBY)



def entry_primary_mac(entry: Any) -> str | None:
    """The primary a secondary/standby entry points at."""
    if not entry_is_follower(entry):
        return None
    raw = _setting(entry, CONF_PRIMARY_GATEWAY)
    return dr.format_mac(str(raw)) if raw else None


def entry_delegated_whos(entry: Any) -> set[int]:
    """WHOs delegated to a secondary entry (never to a standby)."""
    if entry_topology(entry) != TOPOLOGY_SHARED or entry_role(entry) != ROLE_SECONDARY:
        return set()
    whos: set[int] = set()
    for item in _setting(entry, CONF_DELEGATED_WHOS) or []:
        try:
            whos.add(int(item))
        except (ValueError, TypeError):
            pass
    return whos


def dependents(hass: HomeAssistant, mac: str) -> list[Any]:
    """The secondary/standby entries that point at ``mac`` as their primary."""
    return [e for e in hass.config_entries.async_entries(DOMAIN) if entry_primary_mac(e) == mac]


def delegated_away_whos(hass: HomeAssistant, mac: str) -> set[int]:
    """WHOs a primary leaves to its secondaries."""
    whos: set[int] = set()
    for entry in dependents(hass, mac):
        whos |= entry_delegated_whos(entry)
    return whos


def topology_signature(entry: Any) -> tuple[Any, ...]:
    """What a reload has to pick up when it changes."""
    return (
        entry_topology(entry),
        entry_role(entry),
        entry_primary_mac(entry),
        tuple(sorted(entry_delegated_whos(entry))),
    )


@callback
def async_check_primary_links(hass: HomeAssistant, *, removed: str | None = None) -> None:
    """Raise a repair issue for each secondary/standby left without a shared primary.

    Such a gateway keeps suppressing discovery for a primary that is gone, so the
    user has to reconfigure it. ``removed`` is an entry being deleted right now.
    """
    from .repairs import async_create_primary_missing_issue, async_delete_primary_missing_issue

    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id == removed:
            continue
        primary = entry_primary_mac(entry)
        target = entry_for_mac(hass, primary, exclude=removed) if primary else None
        if not entry_is_follower(entry) or (
            target is not None and entry_topology(target) == TOPOLOGY_SHARED and entry_role(target) == ROLE_PRIMARY
        ):
            async_delete_primary_missing_issue(hass, entry.entry_id)
        else:
            async_create_primary_missing_issue(hass, entry.entry_id, entry.title, primary or "-")


def entry_for_mac(hass: HomeAssistant, mac: str, *, exclude: str | None = None) -> Any | None:
    """The config entry of the gateway with ``mac`` (ignoring entry id ``exclude``)."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id != exclude and entry_mac(entry) == mac:
            return entry
    return None


def peer_unique_id(unique_id: str, own_mac: str, peer_mac: str) -> str | None:
    """``unique_id`` rewritten onto ``peer_mac`` (entity unique ids start with the gateway MAC)."""
    if unique_id.startswith(own_mac):
        return f"{peer_mac}{unique_id[len(own_mac):]}"
    clean_own = own_mac.replace(":", "").lower()
    if unique_id.lower().startswith(clean_own):
        return f"{peer_mac.replace(':', '').lower()}{unique_id[len(clean_own):]}"
    return None
