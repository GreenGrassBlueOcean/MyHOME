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
import asyncio

from homeassistant.components.media_player.const import MediaPlayerState
from homeassistant.core import HomeAssistant

from .const import LOGGER


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
    _IDLE_STATES: frozenset[MediaPlayerState | None] = frozenset({
        MediaPlayerState.IDLE,
        MediaPlayerState.OFF,
        None,  # entity not yet registered / state unknown
    })

    def __init__(
        self,
        hass: HomeAssistant,
        decoder_map: dict[str, int],
        pre_gain_map: dict[str, int] | None = None,
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
        self._lock = asyncio.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_configured(self) -> bool:
        """Return ``True`` if at least one decoder has been mapped."""
        return len(self._decoder_map) > 0

    async def claim(
        self,
        zone_entity_id: str,
        preferred_source: int | None = None,
        environment: str | None = None,
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
        async with self._lock:
            # If this zone was a member of a group, detach it before claiming its own decoder
            self._remove_member_locked(zone_entity_id)

            # If this zone already owns a decoder, reuse it (idempotent).
            for dec_id, owner in self._assignments.items():
                if owner == zone_entity_id:
                    LOGGER.debug("Decoder %s already claimed by %s", dec_id, zone_entity_id)
                    return (dec_id, self._decoder_map[dec_id])

            if environment is not None:
                owner = self.environment_owner(environment, exclude=zone_entity_id)
                if owner is not None:
                    group_members = self._groups.get(zone_entity_id, set())
                    if owner not in group_members:
                        raise EnvironmentBusyError(environment, owner)

            # Candidates in slot order, but a decoder wired to the caller's
            # preferred source comes first: routing the matrix to the input
            # the room already defaults to avoids an audible source switch.
            candidates = list(self._assignments)
            if preferred_source is not None:
                candidates.sort(
                    key=lambda dec: self._decoder_map.get(dec) != preferred_source
                )

            # Find the first decoder that is unassigned AND idle.
            for dec_id in candidates:
                owner = self._assignments[dec_id]
                if owner is not None:
                    continue  # already in use by another zone

                state = self._hass.states.get(dec_id)
                state_val = state.state if state else None

                if state_val in self._IDLE_STATES:
                    self._assignments[dec_id] = zone_entity_id
                    if environment is not None:
                        self._environments[zone_entity_id] = environment
                    LOGGER.info(
                        "DecoderPool: %s claimed by zone %s (source %s)",
                        dec_id,
                        zone_entity_id,
                        self._decoder_map[dec_id],
                    )
                    return (dec_id, self._decoder_map[dec_id])

            # All decoders are busy.
            LOGGER.warning(
                "DecoderPool: all decoders busy — zone %s cannot play", zone_entity_id
            )
            return None

    async def add_member(
        self,
        leader_entity_id: str,
        member_entity_id: str,
        environment: str | None = None,
    ) -> tuple[str, int] | None:
        """Add a member zone to the group of leader_entity_id.

        The member shares the leader's claimed decoder (if one is active).
        If the member is in an environment where another zone is already streaming
        from a different decoder, an EnvironmentBusyError is raised.

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
            # Check idempotency
            if member_entity_id in self._groups.get(leader_entity_id, set()):
                dec_id = None
                for d_id, owner in self._assignments.items():
                    if owner == leader_entity_id:
                        dec_id = d_id
                        break
                if dec_id is None:
                    return None
                return (dec_id, self._decoder_map[dec_id])

            # 1. If leader was a member of another group, detach it
            self._remove_member_locked(leader_entity_id)

            # 2. If member was leader of a group, disband it and release decoder
            if member_entity_id in self._groups:
                self._disband_group_locked(member_entity_id)
            for d_id, owner in self._assignments.items():
                if owner == member_entity_id:
                    self._assignments[d_id] = None
                    self._environments.pop(member_entity_id, None)

            # 3. If member was a member of another group, detach it
            self._remove_member_locked(member_entity_id)

            # Find decoder held by leader
            dec_id = None
            for d_id, owner in self._assignments.items():
                if owner == leader_entity_id:
                    dec_id = d_id
                    break

            # Environment collision check
            if environment is not None:
                owner = self.environment_owner(environment, exclude=member_entity_id)
                if owner is not None:
                    owner_dec = self.get_assignment(owner)
                    if owner_dec is not None and owner_dec != dec_id:
                        raise EnvironmentBusyError(environment, owner)
                    if dec_id is not None and owner_dec is None and owner != leader_entity_id:
                        raise EnvironmentBusyError(environment, owner)
                self._environments[member_entity_id] = environment

            if leader_entity_id not in self._groups:
                self._groups[leader_entity_id] = set()
            self._groups[leader_entity_id].add(member_entity_id)

            LOGGER.info(
                "DecoderPool: zone %s joined group of %s (decoder %s)",
                member_entity_id,
                leader_entity_id,
                dec_id,
            )

            if dec_id is None:
                return None
            return (dec_id, self._decoder_map[dec_id])

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
                if not members:
                    self._groups.pop(leader_id, None)
                self._environments.pop(member_entity_id, None)
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
        for mem in members:
            self._environments.pop(mem, None)
        if members:
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

    async def release(self, zone_entity_id: str) -> str | None:
        """Release the decoder assigned to *zone_entity_id* or detach from group.

        If *zone_entity_id* is a member of a group, only the member is removed.
        If *zone_entity_id* is the group leader, the decoder is released and
        all members are disbanded.

        Args:
            zone_entity_id: The ``entity_id`` of the BTicino zone releasing
                its decoder.

        Returns:
            The freed ``decoder_entity_id``, or ``None`` if the zone had no
            active assignment.

        Example::

            freed = await pool.release("media_player.audio_zone_3")
        """
        async with self._lock:
            # Check if this zone is a member
            member_freed = self._remove_member_locked(zone_entity_id)
            if member_freed is not None:
                return member_freed

            # Check if this zone is a leader with a group
            self._disband_group_locked(zone_entity_id)

            # Check if this zone owns a decoder
            for dec_id, owner in self._assignments.items():
                if owner == zone_entity_id:
                    self._assignments[dec_id] = None
                    self._environments.pop(zone_entity_id, None)
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
            has no active stream.
        """
        for zone, zone_environment in self._environments.items():
            if zone != exclude and zone_environment == environment:
                return zone
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
        """Return all configured decoder entity IDs."""
        return list(self._decoder_map.keys())

    def __repr__(self) -> str:  # pragma: no cover
        busy = sum(1 for v in self._assignments.values() if v is not None)
        members = sum(len(m) for m in self._groups.values())
        return (
            f"<DecoderPool decoders={len(self._decoder_map)} "
            f"busy={busy}/{len(self._decoder_map)} members={members}>"
        )
