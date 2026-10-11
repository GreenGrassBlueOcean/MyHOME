"""Tuner decoding, checked against frames recorded from a live F500N on an MH200N.

The frames below are copied from ``tests/fixtures/traces/f500_tuner``; the
WHO=16 forms are the same tuner's mirrored reports, so both families must
agree on every fact they share.
"""

from __future__ import annotations

import pytest

from custom_components.myhome.tuner_decode import (
    FM_MAX_KHZ,
    FM_MIN_KHZ,
    TunerReport,
    decode_rds_frame,
    decode_who22_tuner,
    frequency_khz_from_who16,
    frequency_khz_from_who22,
    parse_tuner_pictures,
    preset_for_frequency,
    rds_text,
)


def _values(frame: str) -> tuple[int, list[str]]:
    """Split ``*#22*5#2#1*<DIM>*<VALUES...>##`` into (dimension, values)."""
    parts = frame.strip("#").split("*")
    return int(parts[3]), parts[4:]


@pytest.mark.parametrize(
    ("frame", "khz"),
    [
        ("*#22*5#2#1*5*1*8880##", 88800),
        ("*#22*5#2#1*5*1*9620##", 96200),
        ("*#22*5#2#1*5*1*9030##", 90300),
        ("*#22*5#2#1*5*1*10350##", 103500),
    ],
)
def test_who22_frequency_is_in_ten_khz_units(frame: str, khz: int) -> None:
    dimension, values = _values(frame)
    assert decode_who22_tuner(dimension, values) == TunerReport(frequency_khz=khz)


def test_who22_and_who16_frequencies_agree() -> None:
    """``*#16*101*6*0*96200##`` and ``*#22*5#2#1*5*1*9620##`` are one fact."""
    assert frequency_khz_from_who22("9620") == frequency_khz_from_who16("96200") == 96200


@pytest.mark.parametrize(
    ("frame", "khz", "preset"),
    [
        ("*#22*5#2#1*11*1*8880*1##", 88800, 1),
        ("*#22*5#2#1*11*1*9620*2##", 96200, 2),
        ("*#22*5#2#1*11*1*9030*3##", 90300, 3),
        ("*#22*5#2#1*11*1*10350*4##", 103500, 4),
    ],
)
def test_who22_frequency_and_preset(frame: str, khz: int, preset: int) -> None:
    dimension, values = _values(frame)
    assert decode_who22_tuner(dimension, values) == TunerReport(
        frequency_khz=khz, preset=preset
    )


def test_preset_zero_is_a_frequency_without_a_stored_station() -> None:
    assert decode_who22_tuner(11, ["1", "8950", "0"]) == TunerReport(frequency_khz=89500)


@pytest.mark.parametrize("preset", [1, 2, 3, 4])
def test_who22_station_report(preset: int) -> None:
    dimension, values = _values(f"*#22*2#1*6*{preset}##")
    assert decode_who22_tuner(dimension, values) == TunerReport(preset=preset)


def test_rds_decodes_station_names() -> None:
    dimension, values = _values("*#22*5#2#1*10*75*82*79*78*69*72*73*84##")
    assert decode_who22_tuner(dimension, values) == TunerReport(rds="KRONEHIT")
    dimension, values = _values("*#22*5#2#1*10*107*114*111*110*101*104*105*116##")
    assert decode_who22_tuner(dimension, values) == TunerReport(rds="kronehit")


def test_rds_text_of_a_retune_is_blank_not_missing() -> None:
    dimension, values = _values("*#22*5#2#1*10*32*32*32*32*32*32*32*32##")
    report = decode_who22_tuner(dimension, values)
    assert report == TunerReport(rds=None, rds_blank=True)


def test_rds_rotating_text_keeps_its_padding_characters() -> None:
    """Some stations rotate ``*RADIO* ``; the asterisks are real RDS characters."""
    dimension, values = _values("*#22*5#2#1*10*42*82*65*68*73*79*42*32##")
    assert decode_who22_tuner(dimension, values) == TunerReport(rds="*RADIO*")


def test_a_twelve_code_rds_frame_is_dropped_as_a_bus_glitch() -> None:
    values = "42*42*79*79*69*42*79*79*69*42*42*32".split("*")
    assert len(values) == 12
    assert decode_rds_frame(values) is None
    assert decode_who22_tuner(10, values) is None


@pytest.mark.parametrize(
    ("dimension", "values"),
    [
        (5, ["1"]),  # short
        (5, ["1", "96200"]),  # kHz where 10 kHz units belong: 962 MHz
        (5, ["1", "abc"]),
        (11, ["1", "9620"]),  # preset missing
        (11, ["1", "50", "2"]),  # below the FM band
        (6, ["0"]),  # preset numbers start at 1
        (99, ["1"]),  # a dimension this module does not know
        (None, []),
    ],
)
def test_malformed_or_unknown_frames_yield_nothing(dimension, values) -> None:
    assert decode_who22_tuner(dimension, values) is None


def test_fm_band_bounds() -> None:
    assert frequency_khz_from_who22(str(FM_MIN_KHZ // 10)) == FM_MIN_KHZ
    assert frequency_khz_from_who22(str(FM_MAX_KHZ // 10)) == FM_MAX_KHZ
    assert frequency_khz_from_who22(str(FM_MIN_KHZ // 10 - 1)) is None
    assert frequency_khz_from_who22(str(FM_MAX_KHZ // 10 + 1)) is None
    assert frequency_khz_from_who16(str(FM_MAX_KHZ + 1)) is None


def test_rds_text_drops_control_codes() -> None:
    assert rds_text(["72", "5", "73"]) == "HI"
    assert rds_text(["32"] * 8) is None


def test_preset_follows_the_live_frequency_not_the_other_way_round() -> None:
    presets = {1: 88800, 2: 96200, 3: 90300}
    assert preset_for_frequency(96200, presets) == 2
    # An unsaved station gets no preset, so it cannot inherit one's identity.
    assert preset_for_frequency(89500, presets) is None

def test_tuner_pictures_parse_one_entry_per_line() -> None:
    text = "96.2=/local/radio/one.png\n 103.5 = https://example.org/two.png \n"
    assert parse_tuner_pictures(text) == {
        96200: "/local/radio/one.png",
        103500: "https://example.org/two.png",
    }


@pytest.mark.parametrize(
    "line",
    [
        "no separator",
        "96.2=",  # no picture
        "96.2=relative/path.png",  # neither a local path nor an http(s) URL
        "96.2=javascript:alert(1)",
        "abc=/local/x.png",
        "50.0=/local/x.png",  # not FM
        "962=/local/x.png",  # 962 MHz: kHz typed where MHz belongs
    ],
)
def test_tuner_pictures_skip_a_bad_line_not_the_list(line: str) -> None:
    assert parse_tuner_pictures(f"{line}\n88.8=/local/ok.png") == {88800: "/local/ok.png"}


def test_tuner_pictures_empty() -> None:
    assert parse_tuner_pictures(None) == {}
    assert parse_tuner_pictures("") == {}
