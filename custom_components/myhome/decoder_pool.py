"""Decoder pool manager for the MyHOME Dynamic Proxy.

Manages a pool of streaming decoders (squeezelite / Cambridge Audio) that are
physically connected to the BTicino F441M matrix source inputs.  The proxy
intercepts Music Assistant / Spotify play_media commands, claims an idle decoder
from this pool, routes the BTicino matrix to the correct source input, and
forwards the stream URL to the backend decoder.

Architecture
------------
- One ``DecoderPool`` instance per gateway, keyed by MAC address in
  ``entry.runtime_data.decoder_pool``.
- Survives entity reloads (lives on the config entry, not inside an entity).
- Thread-safe: all claim/release operations are serialised with a single
  ``asyncio.Lock`` to prevent race conditions when multiple zones compete for
  the last available decoder.
- State-aware: inspects the live HA entity state of each decoder to determine
  whether it is truly idle before claiming.
- Restart-aware: claims and groups are kept in a :class:`~homeassistant.helpers.storage.Store`
  and taken back after a restart or reload, but only once the bus and the
  decoder confirm them (see "Restoring claims" below).

Restoring claims
----------------
The amplifiers and the decoders keep playing while Home Assistant restarts, so
an empty pool would show a leader alone while other rooms still play its
stream.  The stored claims are therefore kept as *candidates* and turned into
real claims one at a time, when the evidence is in: every zone of the claim has
reported ON on the bus, and the decoder is playing.  A zone reporting OFF, a
decoder that is idle, paused or off, another claim on the same decoder or
zone, or the restore window running out drops the candidate.  Groups whose
leader holds no decoder are not kept: nothing tells whether they still exist.

Gain staging (anti-hiss)
------------------------
Each decoder carries an optional ``pre_gain`` offset (0–50 %).  When the user
adjusts the BTicino zone volume the proxy also sets the decoder volume to
``zone_volume + pre_gain``, capped at 1.0.  This keeps the analog signal level
high and the BTicino amplifier gain low, which reduces the inherent noise floor
of the 2-wire bus.

Typical values
--------------
- Cambridge Audio with Pre-Amp OFF: ``pre_gain = 0`` (already at full line level)
- Squeezelite / piCorePlayer:       ``pre_gain = 20``
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.media_player.const import MediaPlayerState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, LOGGER

STORAGE_VERSION = 1
_SAVE_DELAY = 1.0  # seconds; bursts of joins and leaves are written once

# Decoder states that mean music is coming out, or about to: a track change
# or a Spotify Connect handshake passes through "buffering".
DECODER_PLAYING_STATES = frozenset({
    MediaPlayerState.PLAYING,
    MediaPlayerState.BUFFERING,
    "playing",
    "buffering",
})


def audio_group_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    """Return the store that keeps one gateway's decoder claims across restarts."""
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}.audio_groups_{entry_id}")


@dataclass
class GroupChange:
    """What :meth:`DecoderPool.set_group` changed, for the caller to act on.

    The pool only keeps the books; the amplifiers and decoders behind these
    zones are switched by the media player entities.
    """

    joined: list[str] = field(default_factory=list)
    """Zones that were not in the group before."""
    left: list[str] = field(default_factory=list)
    """Former members that are no longer in the group."""
    orphaned: list[str] = field(default_factory=list)
    """Members of groups that a joining zone used to lead, now disbanded."""
    released: list[str] = field(default_factory=list)
    """Decoders that joining zones held and gave up."""


@dataclass(frozen=True)
class RestoredGroup:
    """A decoder claim, and the rooms that follow it, taken back after a restart."""

    leader: str
    decoder: str
    source: int
    members: tuple[str, ...] = ()
    environments: Mapping[str, str] = field(default_factory=dict)
    """Environment digit per zone, for the zones that have one."""

    @property
    def zones(self) -> tuple[str, ...]:
        """The leader followed by its members."""
        return (self.leader, *self.members)

    def as_dict(self) -> dict[str, Any]:
        """Return the JSON form kept in the store."""
        return {
            "leader": self.leader,
            "decoder": self.decoder,
            "source": self.source,
            "members": list(self.members),
            "environments": dict(self.environments),
        }

    @classmethod
    def from_dict(cls, raw: object) -> RestoredGroup | None:
        """Parse one stored claim; ``None`` when it is not shaped like one."""
        if not isinstance(raw, dict):
            return None
        leader, decoder, source = raw.get("leader"), raw.get("decoder"), raw.get("source")
        members, environments = raw.get("members"), raw.get("environments")
        if not (
            isinstance(leader, str)
            and isinstance(decoder, str)
            and isinstance(source, int)
            and isinstance(members, list)
            and all(isinstance(zone, str) for zone in members)
            and isinstance(environments, dict)
            and all(isinstance(zone, str) and isinstance(env, str) for zone, env in environments.items())
        ):
            return None
        return cls(leader, decoder, source, tuple(members), environments)


class EnvironmentBusyError(Exception):
    """Another zone in the same environment already streams from a decoder.

    The F441M routes per output and an output serves a whole environment, so
    one environment can only ever listen to one matrix input.  Handing a second
    decoder to a zone in that environment would re-route the first zone onto
    the new stream while Home Assistant still shows it playing the old one.
    """

    def __init__(self, environment: str, owner: str) -> None:
        super().__init__(f"environment {environment} is already streaming to {owner}")
        self.environment = environment
        self.owner = owner


class DecoderPool:
    """Thread-safe pool of streaming decoders mapped to BTicino source inputs.

    Each decoder (squeezelite, Cambridge Audio, etc.) is physically connected
    to one of the 4 BTicino source inputs.  This class handles:

    - Thread-safe allocation via ``asyncio.Lock``
    - State-aware idle detection (inspects live HA entity state)
    - Pre-gain configuration per decoder (gain staging / anti-hiss)
    - Graceful release on zone turn-off or options reload
    """

    # HA states that mean "this decoder is available for claiming".
    # UNAVAILABLE is intentionally excluded: treat an offline Cambridge as busy
    # rather than risking a claim on a device that cannot actually play.
    _IDLE_STATES: frozenset[MediaPlayerState | str | None] = frozenset({
        MediaPlayerState.IDLE,
        MediaPlayerState.OFF,
        MediaPlayerState.PAUSED,
        MediaPlayerState.STANDBY,
        "idle",
        "off",
        "paused",
        "standby",
        None,  # entity not yet registered / state unknown
    })

    def __init__(
        self,
        hass: HomeAssistant,
        decoder_map: dict[str, int],
        pre_gain_map: dict[str, int] | None = None,
        stream_incompatible: Collection[str] = (),
        companion_map: Mapping[str, str] | None = None,
        store: Store[dict[str, Any]] | None = None,
    ) -> None:
        """Initialise the decoder pool.

        Args:
            hass: Home Assistant instance (used to read entity states).
            decoder_map: Mapping of ``{entity_id: source_num (int)}``, e.g.::

                {
                    "media_player.cambridge_audio_cxn": 1,
                    "media_player.hifiberry_zone": 2,
                }

                The source number tells the integration which physical F441M input
                the decoder is wired to. For normal streaming the integration activates
                the zone with a simple OFF→ON sequence and trusts the matrix routing
                (set physically or by gateway scenario). The number is available if
                explicit routing commands are ever needed.

            pre_gain_map: Optional mapping of ``{entity_id: pre_gain_pct}``
                where ``pre_gain_pct`` is an integer between 0 and 50.
                Defaults to 0 for any decoder not listed.

            stream_incompatible: Decoders whose integration does not accept
                a stream URL through ``play_media`` (``cambridge_audio``).
                They stay in the pool for passive mirroring and for the
                media types they do accept, but a URL stream skips them.

            companion_map: Optional mapping of ``{decoder_id: streaming_companion_id}``
                where a hardware decoder (e.g. ``cambridge_audio``) is dynamically
                bridged to its companion DLNA DMR entity for URL streaming.

            store: Optional store that keeps the claims across restarts.
                Without one the books live in memory only.

        Example::

            pool = DecoderPool(
                hass,
                decoder_map={"media_player.cambridge_audio_cxn": 1},
                pre_gain_map={"media_player.cambridge_audio_cxn": 0},
            )
        """
        self._hass = hass
        self._decoder_map: dict[str, int] = decoder_map          # entity_id → source_num
        self._pre_gain_map: dict[str, int] = pre_gain_map or {}  # entity_id → pre_gain %
        self._assignments: dict[str, str | None] = {             # entity_id → zone_entity_id (leader) or None
            entity_id: None for entity_id in decoder_map
        }
        self._groups: dict[str, set[str]] = {}                   # leader_entity_id → set of member_entity_ids
        self._environments: dict[str, str] = {}                   # zone_entity_id → environment
        self._stream_incompatible: frozenset[str] = frozenset(stream_incompatible)
        self._companion_map: dict[str, str] = dict(companion_map or {})
        self._former_leaders: dict[str, tuple[str, float]] = {}  # member -> (former_leader, monotonic_time)
        self._lock = asyncio.Lock()
        self._store = store
        self._persist = store is not None
        self._save_pending = False
        self._last_snapshot: dict[str, Any] | None = None  # what the store holds, or will hold
        self._restorable: list[RestoredGroup] = []  # stored claims awaiting confirmation
        self._reported: dict[str, bool] = {}  # zone -> ON/OFF as last reported on the bus

    # ── Persistence ───────────────────────────────────────────────────────────

    async def async_load(self) -> None:
        """Read the claims of the previous run as candidates; the books stay empty.

        Candidates naming a decoder that is no longer configured, or is now
        wired to another matrix input, are dropped here: the installation has
        changed since they were written.
        """
        if self._store is None:
            return
        data = await self._store.async_load()
        stored = data if isinstance(data, dict) else {}
        raw_claims = stored.get("claims")
        self._last_snapshot = {"claims": raw_claims if isinstance(raw_claims, list) else []}
        for raw in self._last_snapshot["claims"]:
            claim = RestoredGroup.from_dict(raw)
            if claim is None:
                LOGGER.debug("DecoderPool: ignoring a malformed stored claim: %r", raw)
            elif self._decoder_map.get(claim.decoder) != claim.source:
                LOGGER.info(
                    "DecoderPool: not restoring %s on decoder %s: it is no longer wired to input %s",
                    claim.leader,
                    claim.decoder,
                    claim.source,
                )
            else:
                self._restorable.append(claim)

    async def async_shutdown(self) -> None:
        """Write out unsaved changes and stop persisting.

        Called when the entry unloads, before the books are emptied: removing
        the zones and releasing the decoders on a reload is not the user
        ending the music, and must not wipe what the next run restores.
        """
        if self._store is not None and self._save_pending:
            await self._store.async_save(self._snapshot())
            self._save_pending = False
        self._persist = False

    def _snapshot(self) -> dict[str, Any]:
        """Return the claims worth keeping: live ones first, then those still awaiting proof."""
        claims: list[RestoredGroup] = []
        for decoder, leader in self._assignments.items():
            if leader is not None:
                zones = [leader, *sorted(self._groups.get(leader, ()))]
                claims.append(
                    RestoredGroup(
                        leader,
                        decoder,
                        self._decoder_map[decoder],
                        tuple(zones[1:]),
                        {zone: self._environments[zone] for zone in zones if zone in self._environments},
                    )
                )
        claims.extend(c for c in self._restorable if self._assignments.get(c.decoder) is None)
        return {"claims": [claim.as_dict() for claim in claims]}

    def _schedule_save(self) -> None:
        """Queue a write of the books if they differ from what the store holds."""
        if self._store is None or not self._persist:
            return
        snapshot = self._snapshot()
        if snapshot == self._last_snapshot:
            return
        self._last_snapshot = snapshot
        self._save_pending = True
        self._store.async_delay_save(self._data_to_save, _SAVE_DELAY)

    def _data_to_save(self) -> dict[str, Any]:
        """Return the data of a delayed write, as of the moment it happens."""
        self._save_pending = False
        return self._snapshot()

    # ── Restoring claims ──────────────────────────────────────────────────────

    @property
    def has_restorable(self) -> bool:
        """Return ``True`` while stored claims still await confirmation."""
        return bool(self._restorable)

    def note_zone_status(self, zone_entity_id: str, is_on: bool) -> None:
        """Record what the bus last reported for a zone; call :meth:`reconcile_restored` next."""
        if self._restorable:
            self._reported[zone_entity_id] = is_on

    def reconcile_restored(self) -> list[RestoredGroup]:
        """Take back the stored claims the evidence now supports, and drop the refuted ones.

        A candidate waits while a zone has not reported yet or the decoder
        has no state, and is decided on the report that completes the evidence.

        Returns:
            The claims that were just put back into the books, for the caller
            to reflect on the entities.
        """
        restored: list[RestoredGroup] = []
        for claim in list(self._restorable):
            reason = self._refutation(claim)
            if reason is None:
                if not self._on_all_zones(claim) or self._decoder_playing(claim.decoder) is None:
                    continue
                self._adopt(claim)
                restored.append(claim)
            else:
                LOGGER.info(
                    "DecoderPool: not restoring %s on decoder %s: %s", claim.leader, claim.decoder, reason
                )
            self._restorable.remove(claim)
        self._schedule_save()
        return restored

    def expire_restorable(self) -> None:
        """Drop every candidate still waiting: the restore window is over."""
        for claim in self._restorable:
            LOGGER.info(
                "DecoderPool: not restoring %s on decoder %s: no confirmation in time",
                claim.leader,
                claim.decoder,
            )
        self._restorable.clear()
        self._reported.clear()
        self._schedule_save()

    def _on_all_zones(self, claim: RestoredGroup) -> bool:
        """Return whether every zone of the claim has reported ON."""
        return all(self._reported.get(zone) for zone in claim.zones)

    def _refutation(self, claim: RestoredGroup) -> str | None:
        """Return why the evidence rules the claim out, or ``None`` when it does not (yet)."""
        if any(self._reported.get(zone) is False for zone in claim.zones):
            return "a zone reported off"
        if self._on_all_zones(claim) and self._decoder_playing(claim.decoder) is False:
            return "the decoder is not playing"
        if self._assignments.get(claim.decoder) is not None or any(
            self.get_group_members(zone) is not None or self.get_assignment(zone) is not None
            for zone in claim.zones
        ):
            return "the decoder or a zone has been claimed since"
        for environment in set(claim.environments.values()):
            if self._environment_owners(environment, claim.zones):
                return f"environment {environment} streams from another decoder"
        return None

    def _decoder_playing(self, decoder_id: str) -> bool | None:
        """Return whether ``decoder_id`` (or its streaming companion) is playing; ``None`` if unknown."""
        states: list[str | None] = []
        for entity_id in dict.fromkeys((decoder_id, self.get_streaming_decoder(decoder_id))):
            state = self._hass.states.get(entity_id)
            reported = state is not None and state.state not in ("unavailable", "unknown")
            states.append(state.state if state is not None and reported else None)
        if any(state in DECODER_PLAYING_STATES for state in states):
            return True
        # One entity of a hardware/companion pair may not report yet: that says nothing.
        return None if None in states else False

    def _adopt(self, claim: RestoredGroup) -> None:
        """Put a confirmed claim into the books."""
        self._assignments[claim.decoder] = claim.leader
        if claim.members:
            self._groups[claim.leader] = set(claim.members)
        self._environments.update(claim.environments)
        LOGGER.info(
            "DecoderPool: restored %s on decoder %s with members %s",
            claim.leader,
            claim.decoder,
            list(claim.members),
        )

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_configured(self) -> bool:
        """Return ``True`` if at least one decoder has been mapped."""
        return len(self._decoder_map) > 0

    @property
    def stream_incompatible(self) -> frozenset[str]:
        """Return the decoders that cannot be handed a stream URL."""
        return self._stream_incompatible

    @property
    def companion_map(self) -> dict[str, str]:
        """Return mapping of decoder_id -> streaming companion entity_id."""
        return dict(self._companion_map)

    def get_streaming_decoder(self, decoder_id: str) -> str:
        """Return the streaming companion entity for decoder_id if one exists, else decoder_id."""
        return self._companion_map.get(decoder_id, decoder_id)

    def _is_decoder_hw_idle(self, dec_id: str) -> bool:
        """Return True if decoder entity (and any companion) is in an idle state."""
        state = self._hass.states.get(dec_id)
        state_val = state.state if state else None
        target_dec_id = self.get_streaming_decoder(dec_id)
        target_state = self._hass.states.get(target_dec_id) if target_dec_id != dec_id else None
        target_state_val = target_state.state if target_state else None
        return state_val in self._IDLE_STATES and (target_dec_id == dec_id or target_state_val in self._IDLE_STATES)

    async def claim(
        self,
        zone_entity_id: str,
        preferred_source: int | None = None,
        environment: str | None = None,
        exclude: Collection[str] = (),
    ) -> tuple[str, int] | None:
        """Claim an idle decoder for *zone_entity_id*.

        Thread-safe: uses ``asyncio.Lock`` to prevent two zones from claiming
        the same decoder simultaneously.

        If *zone_entity_id* already owns a decoder (e.g. song change), the
        existing assignment is returned immediately without re-locking.

        Args:
            zone_entity_id: The ``entity_id`` of the BTicino zone requesting
                a decoder (e.g. ``"media_player.audio_zone_3"``).
            preferred_source: Matrix input this zone would rather use. A
                decoder wired to it is claimed first when it is idle;
                otherwise the usual slot order applies.
            environment: Environment digit of the zone's amplifier address.
                When given, the claim is refused while another zone in the
                same environment holds a decoder: the matrix can route an
                environment to one input only.
            exclude: Decoders not to hand out, e.g. those that cannot take
                the media about to be played.

        Returns:
            ``(decoder_entity_id, source_num: int)`` if an idle decoder was
            found and claimed, or ``None`` if all decoders are busy.

        Raises:
            EnvironmentBusyError: If another zone in ``environment`` already
                holds a decoder.

        Example::

            result = await pool.claim("media_player.audio_zone_3")
            if result is None:
                raise HomeAssistantError("All inputs are busy!")
            decoder_id, source_num = result
        """
        displaced_owner: str | None = None
        claimed: tuple[str, int] | None = None
        async with self._lock:
            # A member playing on its own leaves its group, but only once it
            # has a decoder: a refused or failed claim keeps it in the group.

            # If this zone already owns a decoder, reuse it (idempotent).
            for dec_id, owner in self._assignments.items():
                if owner == zone_entity_id:
                    LOGGER.debug("Decoder %s already claimed by %s", dec_id, zone_entity_id)
                    self._remove_member_locked(zone_entity_id)
                    return (dec_id, self._decoder_map[dec_id])

            if environment is not None:
                # The zone's own members follow it onto the new decoder.
                ignore = {zone_entity_id, *self._groups.get(zone_entity_id, ())}
                former_leader, former_time = self._former_leaders.get(
                    zone_entity_id, (None, 0.0)
                )
                if (
                    former_leader is not None
                    and (time.monotonic() - former_time) < 30.0
                    and len(self._groups.get(former_leader, set())) == 0
                ):
                    ignore.add(former_leader)
                owners = self._environment_owners(environment, ignore)
                if owners:
                    raise EnvironmentBusyError(environment, owners[0])

            # Candidates in slot order, but a decoder wired to the caller's
            # preferred source comes first: routing the matrix to the input
            # the room already defaults to avoids an audible source switch.
            # Unassigned decoders are always prioritized over assigned ones.
            candidates = list(self._assignments)
            if preferred_source is not None:
                candidates.sort(
                    key=lambda dec: self._decoder_map.get(dec) != preferred_source
                )
            candidates.sort(key=lambda dec: self._assignments[dec] is not None)

            # Find the first decoder that is unassigned AND idle, or can be handed over.
            for dec_id in candidates:
                if dec_id in exclude:
                    continue
                owner = self._assignments[dec_id]
                is_hw_idle = self._is_decoder_hw_idle(dec_id)
                former_leader, former_time = self._former_leaders.get(
                    zone_entity_id, (None, 0.0)
                )
                is_handover = (
                    owner is not None
                    and owner == former_leader
                    and (time.monotonic() - former_time) < 30.0
                    and len(self._groups.get(owner, set())) == 0
                )

                if owner is not None:
                    owner_state = self._hass.states.get(owner)
                    owner_val = owner_state.state if owner_state else None
                    is_owner_off = (
                        is_hw_idle and owner_val in (MediaPlayerState.OFF, "off")
                    )
                    if is_owner_off or is_handover:
                        LOGGER.info(
                            "DecoderPool: reassigning decoder %s from zone %s (state=%s, hw_idle=%s, handover=%s) to %s",
                            dec_id,
                            owner,
                            owner_val,
                            is_hw_idle,
                            is_handover,
                            zone_entity_id,
                        )
                        if owner != zone_entity_id and owner_val not in (MediaPlayerState.OFF, "off"):
                            displaced_owner = owner
                        self._disband_group_locked(owner)
                        self._environments.pop(owner, None)
                        self._assignments[dec_id] = None
                        owner = None
                    else:
                        continue  # already in use by an active zone

                if is_hw_idle or is_handover:
                    self._remove_member_locked(zone_entity_id)
                    self._assignments[dec_id] = zone_entity_id
                    if environment is not None:
                        self._environments[zone_entity_id] = environment
                    self._schedule_save()
                    LOGGER.info(
                        "DecoderPool: %s claimed by zone %s (source %s)",
                        dec_id,
                        zone_entity_id,
                        self._decoder_map[dec_id],
                    )
                    claimed = (dec_id, self._decoder_map[dec_id])
                    break

        if displaced_owner:
            try:
                await self._hass.services.async_call(
                    "media_player", "turn_off", {"entity_id": displaced_owner}
                )
            except Exception as err:
                LOGGER.debug("DecoderPool: failed to turn off displaced zone %s: %s", displaced_owner, err)

        if claimed:
            return claimed

        # All decoders are busy.
        LOGGER.warning(
            "DecoderPool: all decoders busy — zone %s cannot play", zone_entity_id
        )
        return None

    async def set_group(
        self,
        leader_entity_id: str,
        members: Mapping[str, str | None],
    ) -> GroupChange:
        """Make ``members`` the complete member list of ``leader_entity_id``'s group.

        Snapshot semantics, as ``media_player.join`` expects: members not
        listed leave, listed zones join. Every environment is checked before
        anything changes, so a refused join leaves the pool exactly as it
        was. A joining zone gives up any decoder it held and the group it
        led; both are reported back so the caller can stop that decoder and
        switch those amplifiers.

        Args:
            leader_entity_id: The zone that leads the group.
            members: ``{member_entity_id: environment}``; the environment may
                be ``None`` when the zone has no routing address.

        Returns:
            A :class:`GroupChange` describing the zones and decoders affected.

        Raises:
            EnvironmentBusyError: If a member's environment is streaming from
                a decoder other than the leader's.
        """
        async with self._lock:
            return self._set_group_locked(leader_entity_id, dict(members))

    def _set_group_locked(
        self, leader_entity_id: str, members: dict[str, str | None]
    ) -> GroupChange:
        """Validate, then apply, a group snapshot while holding ``self._lock``."""
        members.pop(leader_entity_id, None)
        current = self._groups.get(leader_entity_id, set())
        joining = [zone for zone in members if zone not in current]
        leaving = sorted(current - members.keys())

        # Zones whose environment claims are about to go: the members
        # themselves, those leaving, and the groups joining zones used to lead.
        vacated = set(members) | set(leaving)
        for zone in joining:
            vacated |= self._groups.get(zone, set())
        if self.get_leader(leader_entity_id) is not None:
            vacated.add(leader_entity_id)

        decoder = self._owned_decoder(leader_entity_id)
        for zone, environment in members.items():
            if environment is None:
                continue
            for owner in self._environment_owners(environment, vacated):
                if self.get_assignment(owner) != decoder:
                    raise EnvironmentBusyError(environment, owner)

        # Validated: from here on nothing raises.
        change = GroupChange(joined=joining, left=leaving)
        self._remove_member_locked(leader_entity_id)
        for zone in leaving:
            self._remove_member_locked(zone)
        for zone in joining:
            change.orphaned.extend(self._disband_group_locked(zone))
            owned = self._owned_decoder(zone)
            if owned is not None:
                self._assignments[owned] = None
                change.released.append(owned)
            self._remove_member_locked(zone)
        change.orphaned = sorted(set(change.orphaned) - set(members))

        if members:
            self._groups[leader_entity_id] = set(members)
        else:
            self._groups.pop(leader_entity_id, None)
        for zone, environment in members.items():
            if environment is None:
                self._environments.pop(zone, None)
            else:
                self._environments[zone] = environment

        self._schedule_save()
        if joining or leaving:
            LOGGER.info(
                "DecoderPool: group of %s is now %s (decoder %s)",
                leader_entity_id,
                sorted(members),
                decoder,
            )
        return change

    async def add_member(
        self,
        leader_entity_id: str,
        member_entity_id: str,
        environment: str | None = None,
    ) -> tuple[str, int] | None:
        """Add a member zone to the group of leader_entity_id.

        The member shares the leader's claimed decoder (if one is active).
        Nothing changes when the member's environment is streaming from a
        different decoder: :class:`EnvironmentBusyError` is raised first.

        Args:
            leader_entity_id: The zone entity ID that leads the group.
            member_entity_id: The zone entity ID joining the group.
            environment: Optional environment digit of the member zone.

        Returns:
            ``(decoder_entity_id, source_num)`` if the leader holds a decoder,
            or ``None`` if the group is passive / not currently streaming.

        Raises:
            EnvironmentBusyError: If the member's environment is streaming from
                a different decoder.
        """
        async with self._lock:
            members: dict[str, str | None] = {
                zone: self._environments.get(zone)
                for zone in self._groups.get(leader_entity_id, set())
            }
            if member_entity_id not in members:
                members[member_entity_id] = environment
            self._set_group_locked(leader_entity_id, members)
            decoder = self._owned_decoder(leader_entity_id)
            if decoder is None:
                return None
            return (decoder, self._decoder_map[decoder])

    # Alias for explicit group naming
    add_group_member = add_member

    async def remove_member(self, member_entity_id: str) -> str | None:
        """Remove a member zone from whichever group it joined.

        Args:
            member_entity_id: The zone entity ID leaving the group.

        Returns:
            The decoder entity ID the member was listening to, or None if not found.
        """
        async with self._lock:
            return self._remove_member_locked(member_entity_id)

    remove_group_member = remove_member

    def _remove_member_locked(self, member_entity_id: str) -> str | None:
        """Remove a member zone while already holding self._lock."""
        for leader_id, members in list(self._groups.items()):
            if member_entity_id in members:
                members.remove(member_entity_id)
                self._former_leaders[member_entity_id] = (leader_id, time.monotonic())
                if not members:
                    self._groups.pop(leader_id, None)
                self._environments.pop(member_entity_id, None)
                self._schedule_save()
                LOGGER.info(
                    "DecoderPool: member %s removed from leader %s",
                    member_entity_id,
                    leader_id,
                )
                for dec_id, owner in self._assignments.items():
                    if owner == leader_id:
                        return dec_id
                return None
        return None

    def _disband_group_locked(self, leader_entity_id: str) -> list[str]:
        """Disband group members while holding lock."""
        members = list(self._groups.pop(leader_entity_id, set()))
        now = time.monotonic()
        for mem in members:
            self._former_leaders[mem] = (leader_entity_id, now)
            self._environments.pop(mem, None)
        if members:
            self._schedule_save()
            LOGGER.info(
                "DecoderPool: group of %s disbanded (%d members)",
                leader_entity_id,
                len(members),
            )
        return members

    async def disband_group(self, leader_entity_id: str) -> list[str]:
        """Disband a group owned by leader_entity_id."""
        async with self._lock:
            return self._disband_group_locked(leader_entity_id)

    async def transfer_leadership(
        self, old_leader: str, new_leader: str
    ) -> tuple[str, int] | None:
        """Transfer group leadership and active decoder from old_leader to new_leader.

        Args:
            old_leader: Current group leader entity_id.
            new_leader: Member entity_id that will become the new leader.

        Returns:
            ``(decoder_entity_id, source_num)`` if a decoder was transferred, or ``None``.
        """
        async with self._lock:
            return self._transfer_leadership_locked(old_leader, new_leader)

    def _transfer_leadership_locked(
        self, old_leader: str, new_leader: str
    ) -> tuple[str, int] | None:
        """Transfer group leadership while holding self._lock."""
        if old_leader not in self._groups or new_leader not in self._groups[old_leader]:
            return None
        current_members = self._groups.pop(old_leader, set())
        remaining = current_members - {new_leader}
        if remaining:
            self._groups[new_leader] = remaining
        else:
            self._groups.pop(new_leader, None)

        decoder = None
        for dec_id, owner in self._assignments.items():
            if owner == old_leader:
                self._assignments[dec_id] = new_leader
                decoder = dec_id
                break

        self._environments.pop(old_leader, None)
        self._schedule_save()
        LOGGER.info(
            "DecoderPool: leadership of group transferred from %s to %s (members: %s, decoder: %s)",
            old_leader,
            new_leader,
            sorted(remaining),
            decoder,
        )
        if decoder:
            return (decoder, self._decoder_map[decoder])
        return None

    async def release(self, zone_entity_id: str) -> str | None:
        """Release the decoder assigned to *zone_entity_id* or detach from group.

        If *zone_entity_id* is a member of a group, only the member is removed.
        If *zone_entity_id* is the group leader, the decoder is released and
        all members are disbanded.

        Args:
            zone_entity_id: The ``entity_id`` of the BTicino zone releasing
                its decoder.

        Returns:
            The decoder the zone was listening to, or ``None`` if it had no
            active assignment.  Only a leader's decoder is actually freed: for
            a member this is the leader's decoder, which stays claimed.

        Example::

            freed = await pool.release("media_player.audio_zone_3")
        """
        async with self._lock:
            # A member only leaves; the leader keeps the decoder.
            leader_decoder = self._remove_member_locked(zone_entity_id)
            if leader_decoder is not None:
                return leader_decoder

            # Check if this zone is a leader with a group
            self._disband_group_locked(zone_entity_id)

            # Check if this zone owns a decoder
            for dec_id, owner in self._assignments.items():
                if owner == zone_entity_id:
                    self._assignments[dec_id] = None
                    self._environments.pop(zone_entity_id, None)
                    self._schedule_save()
                    LOGGER.info(
                        "DecoderPool: %s released by leader %s (group disbanded)",
                        dec_id,
                        zone_entity_id,
                    )
                    return dec_id
        return None

    async def release_all(self) -> None:
        """Release every decoder assignment and disband all groups.

        Called when the user updates options via the UI so that the pool can be
        rebuilt cleanly.  Any zone currently streaming will lose its decoder;
        the user must re-trigger playback.

        Example::

            await pool.release_all()
        """
        async with self._lock:
            for dec_id in self._assignments:
                self._assignments[dec_id] = None
            self._groups.clear()
            self._environments.clear()
            self._schedule_save()
            LOGGER.info("DecoderPool: all assignments released (options reload)")

    def get_assignment(self, zone_entity_id: str) -> str | None:
        """Return the decoder entity_id assigned to *zone_entity_id*, or ``None``.

        Lock-free read — safe because ``_assignments`` and ``_groups`` mutations
        only happen inside the asyncio event loop under the lock.

        Args:
            zone_entity_id: The ``entity_id`` of the zone to query.

        Returns:
            The ``decoder_entity_id`` currently assigned to the zone, or
            ``None`` if the zone has no active decoder.
        """
        for dec_id, owner in self._assignments.items():
            if owner == zone_entity_id:
                return dec_id
        for leader_id, members in self._groups.items():
            if zone_entity_id in members:
                for dec_id, owner in self._assignments.items():
                    if owner == leader_id:
                        return dec_id
        return None

    def get_group_members(self, entity_id: str) -> list[str] | None:
        """Return group members for entity_id (leader first), or None if not grouped."""
        if entity_id in self._groups and self._groups[entity_id]:
            return [entity_id, *sorted(self._groups[entity_id])]
        for leader_id, members in self._groups.items():
            if members and entity_id in members:
                return [leader_id, *sorted(members)]
        return None

    def get_leader(self, member_entity_id: str) -> str | None:
        """Return the leader entity_id of the group member_entity_id belongs to, or None."""
        for leader_id, members in self._groups.items():
            if member_entity_id in members:
                return leader_id
        return None

    def is_leader(self, entity_id: str) -> bool:
        """Return True if entity_id is currently the leader of an active group."""
        return bool(self._groups.get(entity_id))

    def get_members(self, leader_entity_id: str) -> list[str]:
        """Return the list of member entity IDs joined with *leader_entity_id*."""
        return sorted(self._groups.get(leader_entity_id, set()))

    def get_decoder_for_source(self, source_num: int) -> str | None:
        """Return the decoder entity ID wired to ``source_num``, or ``None``."""
        for dec_id, src in self._decoder_map.items():
            if src == source_num:
                return dec_id
        return None

    def decoder_source(self, decoder_entity_id: str) -> int | None:
        """Return the physical source number (1–4) for *decoder_entity_id*, or ``None``."""
        return self._decoder_map.get(decoder_entity_id)

    def environment_owner(self, environment: str, exclude: str | None = None) -> str | None:
        """Return the zone that streams from a decoder in ``environment``.

        Lock-free read, like :meth:`get_assignment`.  Used to keep automatic
        routing (a zone's default source) from switching an environment away
        from a stream another zone in it is playing.

        Args:
            environment: Environment digit of an amplifier address.
            exclude: Zone to ignore, normally the caller itself.

        Returns:
            The ``entity_id`` of that zone, or ``None`` when the environment
            has no active stream.  Members of a group whose leader holds no
            decoder are not streaming and do not count.
        """
        owners = self._environment_owners(environment, {exclude} if exclude else set())
        return owners[0] if owners else None

    def _environment_owners(self, environment: str, exclude: Collection[str]) -> list[str]:
        """Return every zone outside ``exclude`` actively streaming from a decoder in ``environment``."""
        active = []
        for zone, zone_environment in self._environments.items():
            if zone_environment == environment and zone not in exclude and self.get_assignment(zone) is not None:
                state = self._hass.states.get(zone)
                state_val = state.state if state else None
                if state_val not in (MediaPlayerState.OFF, "off"):
                    active.append(zone)
        return active

    def _owned_decoder(self, zone_entity_id: str) -> str | None:
        """Return the decoder ``zone_entity_id`` claimed itself (not one it shares as a member)."""
        for dec_id, owner in self._assignments.items():
            if owner == zone_entity_id:
                return dec_id
        return None

    def get_pre_gain(self, decoder_entity_id: str) -> int:
        """Return the configured pre-gain offset for *decoder_entity_id*.

        Args:
            decoder_entity_id: The ``entity_id`` of the decoder.

        Returns:
            The pre-gain percent (0–50).  Defaults to ``0`` if not configured.

        Example::

            gain_pct = pool.get_pre_gain("media_player.cambridge_audio_cxn")
            decoder_volume = min(1.0, zone_volume + gain_pct / 100.0)
        """
        return self._pre_gain_map.get(decoder_entity_id, 0)

    # ── Introspection (for listeners and tests) ───────────────────────────────

    @property
    def decoder_entity_ids(self) -> list[str]:
        """Return all configured decoder entity IDs, including any companions."""
        ids = list(self._decoder_map.keys())
        for comp in self._companion_map.values():
            if comp not in ids:
                ids.append(comp)
        return ids

    def __repr__(self) -> str:  # pragma: no cover
        busy = sum(1 for v in self._assignments.values() if v is not None)
        members = sum(len(m) for m in self._groups.values())
        return (
            f"<DecoderPool decoders={len(self._decoder_map)} "
            f"busy={busy}/{len(self._decoder_map)} members={members}>"
        )
