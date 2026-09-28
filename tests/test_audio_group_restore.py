"""Decoder claims and groups survive a restart: stored, then confirmed by the bus.

The amplifiers and decoders keep playing while Home Assistant restarts, so the
pool takes its stored claims back only for zones that report ON and a decoder
that plays, and drops the rest.
"""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.media_player import MediaPlayerState
from homeassistant.const import CONF_MAC
from homeassistant.helpers.storage import Store
from OWNd.message import OWNSoundEvent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myhome import async_remove_entry
from custom_components.myhome import async_unload_entry as unload_gateway_entry
from custom_components.myhome.const import (
    CONF_DECODER_ENTITY,
    CONF_DECODER_SOURCE,
    CONF_ENTITY,
    DOMAIN,
)
from custom_components.myhome.data import MyHOMERuntimeData
from custom_components.myhome.decoder_pool import (
    STORAGE_VERSION,
    DecoderPool,
    RestoredGroup,
    audio_group_store,
)
from custom_components.myhome.media_player import _RESTORE_WINDOW, async_setup_entry
from tests.conftest import attach_runtime
from tests.test_component_media_player import _create_test_zone, _dec_event


@pytest.fixture
def mock_gateway():
    gateway = MagicMock()
    gateway.mac = "00:11:22:33:44:55"
    gateway.send = AsyncMock()
    gateway.send_status_request = AsyncMock()
    return gateway


@pytest.fixture(autouse=True)
def _short_save_delay(monkeypatch):
    """Batched store writes re-arm on the loop clock, so the tests wait in real time."""
    monkeypatch.setattr("custom_components.myhome.decoder_pool._SAVE_DELAY", 0.01)


ENTRY_ID = "restore_entry"
STORE_KEY = f"{DOMAIN}.audio_groups_{ENTRY_ID}"
DECODER = "media_player.dec1"
LEADER = "media_player.zone23"
MEMBER = "media_player.zone36"
OTHER = "media_player.zone41"


def _claim(**overrides):
    raw = {
        "leader": LEADER,
        "decoder": DECODER,
        "source": 2,
        "members": [MEMBER],
        "environments": {LEADER: "2", MEMBER: "3"},
    }
    raw.update(overrides)
    return raw


def _seed(hass_storage, *claims):
    hass_storage[STORE_KEY] = {
        "version": STORAGE_VERSION,
        "minor_version": 1,
        "key": STORE_KEY,
        "data": {"claims": list(claims)},
    }


def _stored(hass_storage):
    return hass_storage[STORE_KEY]["data"]["claims"]


async def _pool(hass, hass_storage, *claims, decoders=None, companion_map=None):
    if claims:
        _seed(hass_storage, *claims)
    pool = DecoderPool(
        hass,
        decoders or {DECODER: 2},
        companion_map=companion_map,
        store=audio_group_store(hass, ENTRY_ID),
    )
    await pool.async_load()
    return pool


async def _flush(hass):
    """Wait out the store's write delay in real time: batched saves re-arm on the loop clock."""
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()


def _report(pool, *zones, on=True):
    for zone in zones:
        pool.note_zone_status(zone, on)


# ── The stored form ──────────────────────────────────────────────────────────


def test_a_claim_survives_the_round_trip_through_json():
    group = RestoredGroup.from_dict(_claim())
    assert group == RestoredGroup(LEADER, DECODER, 2, (MEMBER,), {LEADER: "2", MEMBER: "3"})
    assert group.zones == (LEADER, MEMBER)
    assert RestoredGroup.from_dict(group.as_dict()) == group


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "media_player.zone23",
        {},
        _claim(leader=1),
        _claim(decoder=None),
        _claim(source="2"),
        _claim(members="media_player.zone36"),
        _claim(members=[MEMBER, 4]),
        _claim(environments=[]),
        _claim(environments={LEADER: 2}),
        _claim(environments={3: "2"}),
    ],
)
def test_a_malformed_claim_is_not_a_claim(raw):
    assert RestoredGroup.from_dict(raw) is None


# ── Saving ───────────────────────────────────────────────────────────────────


async def test_claims_and_groups_are_written_as_they_change(hass, hass_storage):
    pool = await _pool(hass, hass_storage)
    assert STORE_KEY not in hass_storage

    assert await pool.claim(LEADER, environment="2") == (DECODER, 2)
    await pool.add_member(LEADER, MEMBER, "3")
    await _flush(hass)
    assert _stored(hass_storage) == [_claim()]

    await pool.remove_member(MEMBER)
    await _flush(hass)
    assert _stored(hass_storage) == [_claim(members=[], environments={LEADER: "2"})]

    await pool.release(LEADER)
    await _flush(hass)
    assert _stored(hass_storage) == []


async def test_leadership_transfer_and_release_all_are_written(hass, hass_storage):
    pool = await _pool(hass, hass_storage)
    await pool.claim(LEADER, environment="2")
    await pool.add_member(LEADER, MEMBER, "3")
    await pool.transfer_leadership(LEADER, MEMBER)
    await _flush(hass)
    assert _stored(hass_storage) == [
        _claim(leader=MEMBER, members=[], environments={MEMBER: "3"})
    ]

    await pool.release_all()
    await _flush(hass)
    assert _stored(hass_storage) == []


async def test_a_change_that_leaves_the_books_alone_writes_nothing(hass, hass_storage):
    pool = await _pool(hass, hass_storage)
    await pool.claim(LEADER, environment="2")
    await _flush(hass)
    hass_storage.pop(STORE_KEY)

    assert await pool.claim(LEADER, environment="2") == (DECODER, 2)  # idempotent
    await pool.release(OTHER)  # never had anything
    await _flush(hass)
    assert STORE_KEY not in hass_storage


async def test_a_pool_without_a_store_keeps_its_books_in_memory(hass):
    pool = DecoderPool(hass, {DECODER: 2})
    await pool.async_load()
    await pool.claim(LEADER)
    await pool.async_shutdown()
    assert pool.get_assignment(LEADER) == DECODER
    assert pool.has_restorable is False


async def test_shutdown_writes_what_is_pending_and_then_stops_writing(hass, hass_storage):
    pool = await _pool(hass, hass_storage)
    await pool.claim(LEADER, environment="2")

    await pool.async_shutdown()
    assert _stored(hass_storage) == [_claim(members=[], environments={LEADER: "2"})]

    # The unload releases everything; that is not the user ending the music.
    await pool.release_all()
    await _flush(hass)
    assert _stored(hass_storage) == [_claim(members=[], environments={LEADER: "2"})]


async def test_shutdown_with_nothing_pending_leaves_the_store_alone(hass, hass_storage):
    pool = await _pool(hass, hass_storage, _claim())
    await pool.async_shutdown()
    assert _stored(hass_storage) == [_claim()]


# ── Loading ──────────────────────────────────────────────────────────────────


async def test_stored_claims_wait_for_confirmation(hass, hass_storage):
    pool = await _pool(hass, hass_storage, _claim())
    assert pool.has_restorable is True
    assert pool.get_assignment(LEADER) is None
    assert pool.get_group_members(LEADER) is None


@pytest.mark.parametrize("data", [None, [], {}, {"claims": "nope"}])
async def test_an_empty_or_odd_store_restores_nothing(hass, hass_storage, data):
    if data is not None:
        hass_storage[STORE_KEY] = {"version": STORAGE_VERSION, "minor_version": 1, "key": STORE_KEY, "data": data}
    pool = DecoderPool(hass, {DECODER: 2}, store=audio_group_store(hass, ENTRY_ID))
    await pool.async_load()
    assert pool.has_restorable is False


async def test_claims_the_installation_has_outgrown_are_dropped(hass, hass_storage, caplog):
    caplog.set_level(logging.DEBUG)
    pool = await _pool(
        hass,
        hass_storage,
        "junk",
        _claim(decoder="media_player.gone"),
        _claim(source=3),  # the decoder is wired to another input now
        decoders={DECODER: 2},
    )
    assert pool.has_restorable is False
    assert "no longer wired to input 3" in caplog.text
    assert "malformed stored claim" in caplog.text

    # The next change rewrites the store without them.
    await pool.claim(LEADER)
    await _flush(hass)
    assert [c["leader"] for c in _stored(hass_storage)] == [LEADER]


# ── Reconciling ──────────────────────────────────────────────────────────────


async def test_a_claim_is_restored_once_every_zone_is_on_and_the_decoder_plays(hass, hass_storage):
    pool = await _pool(hass, hass_storage, _claim())
    hass.states.async_set(DECODER, "playing")

    _report(pool, LEADER)
    assert pool.reconcile_restored() == []  # the member has not answered yet
    assert pool.get_assignment(LEADER) is None

    _report(pool, MEMBER)
    restored = pool.reconcile_restored()

    assert [group.leader for group in restored] == [LEADER]
    assert pool.get_assignment(LEADER) == DECODER
    assert pool.get_assignment(MEMBER) == DECODER
    assert pool.get_group_members(MEMBER) == [LEADER, MEMBER]
    assert pool.environment_owner("3") == MEMBER  # the room's environment is spoken for again
    assert pool._environments == {LEADER: "2", MEMBER: "3"}
    assert pool.has_restorable is False


async def test_the_books_are_not_rewritten_for_a_claim_taken_back_as_stored(hass, hass_storage):
    pool = await _pool(hass, hass_storage, _claim())
    hass.states.async_set(DECODER, "buffering")
    _report(pool, LEADER, MEMBER)
    pool.reconcile_restored()
    hass_storage.pop(STORE_KEY)
    await _flush(hass)
    assert STORE_KEY not in hass_storage


async def test_a_solo_claim_is_restored_without_a_group(hass, hass_storage):
    pool = await _pool(hass, hass_storage, _claim(members=[], environments={}))
    hass.states.async_set(DECODER, "playing")
    _report(pool, LEADER)

    assert [group.zones for group in pool.reconcile_restored()] == [(LEADER,)]
    assert pool.get_assignment(LEADER) == DECODER
    assert pool.get_group_members(LEADER) is None
    assert pool._environments == {}


async def test_a_zone_that_reports_off_ends_the_claim(hass, hass_storage, caplog):
    caplog.set_level(logging.INFO)
    pool = await _pool(hass, hass_storage, _claim())
    hass.states.async_set(DECODER, "playing")

    _report(pool, LEADER)
    _report(pool, MEMBER, on=False)
    assert pool.reconcile_restored() == []
    assert pool.has_restorable is False
    assert "a zone reported off" in caplog.text

    # Turning the room back on later does not resurrect the claim.
    _report(pool, MEMBER)
    assert pool.reconcile_restored() == []
    assert pool.get_assignment(LEADER) is None

    # Nothing left to prove: reports are no longer even kept.
    pool.note_zone_status(OTHER, True)
    assert OTHER not in pool._reported


@pytest.mark.parametrize("state", ["idle", "paused", "off", "standby", "on"])
async def test_a_decoder_that_is_not_playing_ends_the_claim(hass, hass_storage, state, caplog):
    caplog.set_level(logging.INFO)
    pool = await _pool(hass, hass_storage, _claim())
    hass.states.async_set(DECODER, state)
    _report(pool, LEADER, MEMBER)

    assert pool.reconcile_restored() == []
    assert pool.has_restorable is False
    assert pool.get_assignment(LEADER) is None
    assert "the decoder is not playing" in caplog.text


@pytest.mark.parametrize("state", [None, "unavailable", "unknown"])
async def test_a_decoder_that_does_not_report_yet_is_waited_for(hass, hass_storage, state):
    pool = await _pool(hass, hass_storage, _claim())
    if state is not None:
        hass.states.async_set(DECODER, state)
    _report(pool, LEADER, MEMBER)

    assert pool.reconcile_restored() == []
    assert pool.has_restorable is True

    hass.states.async_set(DECODER, "playing")
    assert len(pool.reconcile_restored()) == 1


async def test_a_streaming_companion_is_part_of_the_decoder(hass, hass_storage):
    companion = "media_player.dec1_dlna"
    pool = await _pool(hass, hass_storage, _claim(), companion_map={DECODER: companion})
    _report(pool, LEADER, MEMBER)

    # The hardware entity idles, the companion says nothing yet: no verdict.
    hass.states.async_set(DECODER, "idle")
    assert pool.reconcile_restored() == []
    assert pool.has_restorable is True

    # Either of the two playing is enough.
    hass.states.async_set(companion, "playing")
    assert len(pool.reconcile_restored()) == 1


async def test_a_companion_that_idles_too_ends_the_claim(hass, hass_storage):
    companion = "media_player.dec1_dlna"
    pool = await _pool(hass, hass_storage, _claim(), companion_map={DECODER: companion})
    _report(pool, LEADER, MEMBER)
    hass.states.async_set(DECODER, "idle")
    hass.states.async_set(companion, "idle")

    assert pool.reconcile_restored() == []
    assert pool.has_restorable is False


async def test_a_claim_made_since_the_restart_wins(hass, hass_storage, caplog):
    caplog.set_level(logging.INFO)
    hass.states.async_set(DECODER, "playing")

    # Someone else holds the decoder.
    hass.states.async_set(DECODER, "idle")
    pool = await _pool(hass, hass_storage, _claim())
    await pool.claim(OTHER)
    hass.states.async_set(DECODER, "playing")
    _report(pool, LEADER, MEMBER)
    assert pool.reconcile_restored() == []
    assert pool.get_assignment(OTHER) == DECODER
    assert pool.get_assignment(LEADER) is None

    # A zone of the claim leads another group now.
    pool = await _pool(hass, hass_storage, _claim(), decoders={DECODER: 2, "media_player.dec2": 3})
    await pool.claim(MEMBER, environment="3")
    _report(pool, LEADER, MEMBER)
    assert pool.reconcile_restored() == []
    assert pool.get_assignment(MEMBER) == "media_player.dec2"
    assert "claimed since" in caplog.text


async def test_an_environment_streaming_elsewhere_ends_the_claim(hass, hass_storage, caplog):
    caplog.set_level(logging.INFO)
    hass.states.async_set(DECODER, "playing")
    hass.states.async_set(OTHER, "on")
    pool = await _pool(hass, hass_storage, _claim(), decoders={DECODER: 2, "media_player.dec2": 3})
    await pool.claim(OTHER, environment="3")  # dec1 plays, so this lands on dec2
    assert pool.get_assignment(OTHER) == "media_player.dec2"
    _report(pool, LEADER, MEMBER)

    assert pool.reconcile_restored() == []
    assert "environment 3 streams from another decoder" in caplog.text


async def test_unconfirmed_claims_expire(hass, hass_storage, caplog):
    caplog.set_level(logging.INFO)
    pool = await _pool(hass, hass_storage, _claim())
    _report(pool, LEADER)

    pool.expire_restorable()

    assert pool.has_restorable is False
    assert pool._reported == {}
    assert "no confirmation in time" in caplog.text
    await _flush(hass)
    assert _stored(hass_storage) == []  # the store forgets them too


async def test_waiting_claims_are_kept_in_the_store_across_other_changes(hass, hass_storage):
    pool = await _pool(hass, hass_storage, _claim())
    await pool.claim(OTHER, environment="4")  # another decoder-less pool: dec1 goes to OTHER
    await _flush(hass)
    # dec1 is taken now, so the waiting claim on it is no longer worth keeping.
    assert [c["leader"] for c in _stored(hass_storage)] == [OTHER]

    pool = await _pool(hass, hass_storage, _claim(), decoders={DECODER: 2, "media_player.dec2": 3})
    await pool.claim(OTHER, environment="4", preferred_source=3)
    await _flush(hass)
    assert [c["leader"] for c in _stored(hass_storage)] == [OTHER, LEADER]


# ── The entities ─────────────────────────────────────────────────────────────


def _zones(hass, gateway, hass_storage, *claims, decoder_state="playing"):
    runtime = MyHOMERuntimeData(gateway=gateway)
    pool = DecoderPool(hass, {DECODER: 2}, store=audio_group_store(hass, ENTRY_ID))
    runtime.decoder_pool = pool
    if claims:
        _seed(hass_storage, *claims)
    if decoder_state is not None:
        hass.states.async_set(DECODER, decoder_state)
    leader = _create_test_zone(hass, gateway, runtime, "23", LEADER)
    member = _create_test_zone(hass, gateway, runtime, "36", MEMBER)
    for zone in (leader, member):
        zone.async_write_ha_state = MagicMock()
    return pool, leader, member


def _bus(zone, *, on):
    zone.handle_event(
        MagicMock(
            spec=OWNSoundEvent,
            is_source_event=False,
            where=zone._where,
            is_on=on,
            is_off=not on,
            volume=None,
        )
    )


async def test_the_group_comes_back_when_the_last_room_answers(hass, mock_gateway, hass_storage):
    pool, leader, member = _zones(hass, mock_gateway, hass_storage, _claim())
    await pool.async_load()

    _bus(leader, on=True)
    assert leader.group_members is None
    assert leader.active_decoder is None

    _bus(member, on=True)

    assert leader.active_decoder == DECODER
    assert member.active_decoder is None  # a member follows, it does not own
    assert leader.group_members == [LEADER, MEMBER]
    assert member.group_members == [LEADER, MEMBER]
    # Every room of the group is republished; the caller publishes itself.
    leader.async_write_ha_state.assert_called()
    assert leader.state == MediaPlayerState.PLAYING


async def test_an_off_report_keeps_the_group_from_coming_back(hass, mock_gateway, hass_storage):
    pool, leader, member = _zones(hass, mock_gateway, hass_storage, _claim())
    await pool.async_load()
    leader.hass.async_create_task = MagicMock(side_effect=lambda coro, *a, **k: coro.close())

    _bus(leader, on=True)
    _bus(member, on=False)
    _bus(member, on=True)

    assert leader.group_members is None
    assert leader.active_decoder is None
    assert pool.has_restorable is False


async def test_the_wake_echo_of_an_off_is_not_evidence(hass, mock_gateway, hass_storage):
    pool, leader, member = _zones(hass, mock_gateway, hass_storage, _claim())
    await pool.async_load()
    member._is_wake_echo = MagicMock(return_value=True)

    _bus(member, on=False)

    assert pool.has_restorable is True


async def test_the_group_waits_for_a_decoder_that_comes_up_late(hass, mock_gateway, hass_storage):
    pool, leader, member = _zones(hass, mock_gateway, hass_storage, _claim(), decoder_state=None)
    await pool.async_load()

    _bus(leader, on=True)
    _bus(member, on=True)
    assert leader.group_members is None  # nothing to judge the decoder by yet

    hass.states.async_set(DECODER, "playing")
    leader._async_decoder_state_changed(_dec_event("playing"))

    assert leader.active_decoder == DECODER
    assert member.group_members == [LEADER, MEMBER]


async def test_a_zone_with_nothing_to_restore_does_no_work(hass, mock_gateway, hass_storage):
    pool, leader, member = _zones(hass, mock_gateway, hass_storage)
    await pool.async_load()
    pool.reconcile_restored = MagicMock()

    _bus(leader, on=True)
    leader._async_decoder_state_changed(_dec_event("playing"))

    pool.reconcile_restored.assert_not_called()

    # Neither does a zone that is not part of a gateway runtime.
    with patch.object(type(leader), "_runtime_data", None):
        leader._reconcile_restored_groups(True)


async def test_a_restored_group_whose_leader_entity_is_gone_still_books_the_rooms(hass, mock_gateway, hass_storage):
    pool, leader, member = _zones(hass, mock_gateway, hass_storage, _claim())
    await pool.async_load()
    del leader._runtime_data.media_players[LEADER]

    _bus(member, on=True)
    pool.note_zone_status(LEADER, True)
    member._reconcile_restored_groups()

    assert pool.get_assignment(LEADER) == DECODER
    assert member.group_members == [LEADER, MEMBER]


# ── Setup, unload and removal ────────────────────────────────────────────────


def _entry(hass):
    entry = MagicMock()
    entry.entry_id = ENTRY_ID
    entry.data = {CONF_MAC: "00:11:22:33:44:55"}
    entry.options = {CONF_DECODER_ENTITY.format(1): DECODER, CONF_DECODER_SOURCE.format(1): 2}
    return entry


async def test_setup_loads_the_stored_claims_and_gives_them_a_deadline(hass, mock_gateway, hass_storage):
    _seed(hass_storage, _claim())
    entry = _entry(hass)
    hass.data = {DOMAIN: {entry.data[CONF_MAC]: {CONF_ENTITY: mock_gateway}}}
    timers = []
    cancel = MagicMock()

    def call_later(_hass, delay, action):
        timers.append((delay, action))
        return cancel

    with patch("homeassistant.helpers.entity_registry.async_get"), \
         patch("homeassistant.helpers.entity_registry.async_entries_for_config_entry", return_value=[]), \
         patch("custom_components.myhome.media_player.async_call_later", side_effect=call_later):
        runtime = attach_runtime(hass, entry)
        await async_setup_entry(hass, entry, MagicMock())

    pool = runtime.decoder_pool
    assert pool.has_restorable is True
    assert [delay for delay, _ in timers] == [_RESTORE_WINDOW]
    entry.async_on_unload.assert_any_call(cancel)

    timers[0][1](None)  # the window closes
    assert pool.has_restorable is False


async def test_setup_without_stored_claims_sets_no_timer(hass, mock_gateway, hass_storage):
    entry = _entry(hass)
    hass.data = {DOMAIN: {entry.data[CONF_MAC]: {CONF_ENTITY: mock_gateway}}}

    with patch("homeassistant.helpers.entity_registry.async_get"), \
         patch("homeassistant.helpers.entity_registry.async_entries_for_config_entry", return_value=[]), \
         patch("custom_components.myhome.media_player.async_call_later") as call_later:
        runtime = attach_runtime(hass, entry)
        await async_setup_entry(hass, entry, MagicMock())

    assert runtime.decoder_pool.has_restorable is False
    call_later.assert_not_called()


async def test_a_reload_keeps_the_claims_for_the_next_run(hass, hass_storage):
    mac = "00:03:50:00:12:39"
    entry = MockConfigEntry(domain=DOMAIN, data={"mac": mac, "host": "1.2.3.4", "port": 20000}, unique_id=mac)
    entry.add_to_hass(hass)
    gateway = MagicMock()
    gateway.close_listener = AsyncMock(return_value=True)
    hass.data.setdefault(DOMAIN, {})[mac] = {CONF_ENTITY: gateway}
    runtime = attach_runtime(hass, entry, mac, gateway)
    store_key = f"{DOMAIN}.audio_groups_{entry.entry_id}"
    runtime.decoder_pool = DecoderPool(
        hass, {DECODER: 2}, store=Store(hass, STORAGE_VERSION, store_key)
    )
    await runtime.decoder_pool.claim(LEADER, environment="2")

    with patch.object(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)):
        assert await unload_gateway_entry(hass, entry) is True

    assert hass_storage[store_key]["data"]["claims"][0]["leader"] == LEADER
    assert runtime.decoder_pool.get_assignment(LEADER) is None  # released in memory only


async def test_removing_the_entry_removes_its_claims(hass, hass_storage):
    entry = MockConfigEntry(domain=DOMAIN, data={"mac": "00:03:50:00:12:40"})
    entry.add_to_hass(hass)
    store_key = f"{DOMAIN}.audio_groups_{entry.entry_id}"
    hass_storage[store_key] = {
        "version": STORAGE_VERSION,
        "minor_version": 1,
        "key": store_key,
        "data": {"claims": [_claim()]},
    }

    await async_remove_entry(hass, entry)

    assert store_key not in hass_storage
