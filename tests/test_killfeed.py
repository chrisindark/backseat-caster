"""Automated tests for structured killfeed parsing and multi-kill chains."""

from PIL import Image, ImageDraw

from app.services.highlight.killfeed import (
    KillfeedConfig,
    KillfeedParser,
    KillfeedRow,
    killfeed_sequences_to_events,
    multi_kill_event_type,
    multi_kill_label,
)
from app.services.highlight.ocr import OCRToken
from app.services.highlight.roi_extractor import (
    BatchROIExtractionResult,
    ROIFrame,
    WindowROIExtractionResult,
)

BLUE = (40, 120, 240)
RED = (240, 30, 30)
DARK = (15, 15, 15)


class FakeOCR:
    """Deterministic OCR stub keyed by frame timestamp."""

    def __init__(self, mapping: dict[float, list[OCRToken]]):
        self.mapping = mapping

    def read(self, frame: ROIFrame) -> list[OCRToken]:
        return self.mapping.get(round(frame.timestamp, 3), [])


def token(
    text: str, left: float, top: float, width: float = 100.0, height: float = 20.0
):
    return OCRToken(
        text=text,
        confidence=0.95,
        left=left,
        top=top,
        width=width,
        height=height,
    )


def make_frame(
    timestamp: float,
    left_color: tuple[int, int, int] = BLUE,
    right_color: tuple[int, int, int] = RED,
    width: int = 480,
    height: int = 220,
) -> ROIFrame:
    """Synthetic killfeed frame with a friendly left half and enemy right half."""
    image = Image.new("RGB", (width, height), DARK)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width // 2, height], fill=left_color)
    draw.rectangle([width // 2, 0, width, height], fill=right_color)
    return ROIFrame(
        timestamp=timestamp,
        roi_name="kill_feed",
        width=width,
        height=height,
        raw_rgb=image.tobytes(),
    )


def test_multi_kill_helpers():
    assert multi_kill_label(1) is None
    assert multi_kill_label(2) == "DOUBLE KO"
    assert multi_kill_label(5) == "PENTA KO"
    assert multi_kill_label(7) == "TEAM WIPE"
    assert multi_kill_event_type(3) == "triple_ko"
    assert multi_kill_event_type(1) is None


def test_parse_frame_splits_columns_and_infers_teams():
    parser = KillfeedParser()
    frame = make_frame(10.0)
    rows = parser.parse_frame(
        frame,
        tokens=[token("SPIDERMAN", 20, 40), token("SCARLETWITCH", 300, 42)],
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.actor == "SPIDERMAN"
    assert row.victim == "SCARLETWITCH"
    assert row.action == "elimination"
    assert row.actor_team == "friendly"
    assert row.victim_team == "enemy"
    assert row.timestamp == 10.0
    assert row.confidence > 0.9


def test_parse_frame_extracts_action_and_ability_keyword():
    parser = KillfeedParser(config=KillfeedConfig(ability_keywords=["WEB SHOT"]))
    frame = make_frame(12.0)
    rows = parser.parse_frame(
        frame,
        tokens=[
            token("SPIDERMAN", 20, 40),
            token("WEB SHOT", 170, 40, width=90),
            token("KILLED", 265, 40, width=50),
            token("SCARLETWITCH", 330, 40, width=130),
        ],
    )

    assert len(rows) == 1
    assert rows[0].actor == "SPIDERMAN"
    assert rows[0].victim == "SCARLETWITCH"
    assert rows[0].ability == "WEB SHOT"
    assert rows[0].action == "elimination"


def test_parse_frame_ignores_rows_without_column_gap():
    parser = KillfeedParser()
    frame = make_frame(5.0)
    rows = parser.parse_frame(
        frame,
        tokens=[token("MARY", 20, 40, width=60), token("JANE", 95, 40, width=60)],
    )
    assert rows == []


def test_dedupe_collapses_persistent_rows():
    parser = KillfeedParser()
    row = KillfeedRow(timestamp=10.0, actor="SPIDERMAN", victim="SCARLETWITCH")
    later = row.model_copy(update={"timestamp": 13.0})
    expired = row.model_copy(update={"timestamp": 20.0})

    deduped = parser._dedupe_rows([row, later, expired])
    assert len(deduped) == 2
    assert deduped[0].timestamp == 10.0
    assert deduped[1].timestamp == 20.0


def test_build_sequence_attributes_named_player_chain():
    parser = KillfeedParser(config=KillfeedConfig(player_names=["SPIDERMAN"]))
    rows = [
        KillfeedRow(
            timestamp=10.0, actor="SPIDERMAN", victim="HELA", actor_team="friendly"
        ),
        KillfeedRow(
            timestamp=12.0, actor="SPIDERMAN", victim="LOKI", actor_team="friendly"
        ),
        KillfeedRow(
            timestamp=13.5, actor="SPIDERMAN", victim="THOR", actor_team="friendly"
        ),
        KillfeedRow(
            timestamp=19.0, actor="HELA", victim="SPIDERMAN", actor_team="enemy"
        ),
    ]

    sequence = parser.build_sequence(rows, 0.0, 30.0)

    assert sequence is not None
    assert sequence.attribution_method == "name_match"
    assert sequence.attributed_actor == "SPIDERMAN"
    assert sequence.kill_count == 3
    assert sequence.multi_kill_label == "TRIPLE KO"
    assert sequence.chain_start_seconds == 10.0
    assert sequence.chain_end_seconds == 13.5
    assert sequence.is_player_attributed is True


def test_build_sequence_attributes_friendly_chain_without_names():
    parser = KillfeedParser()
    rows = [
        KillfeedRow(
            timestamp=5.0, actor="MANTIS", victim="HELA", actor_team="friendly"
        ),
        KillfeedRow(
            timestamp=7.0, actor="MANTIS", victim="LOKI", actor_team="friendly"
        ),
    ]
    sequence = parser.build_sequence(rows, 0.0, 20.0)

    assert sequence is not None
    assert sequence.attribution_method == "friendly_chain"
    assert sequence.attributed_actor == "MANTIS"
    assert sequence.kill_count == 2
    assert sequence.multi_kill_label == "DOUBLE KO"


def test_build_sequence_does_not_attribute_enemy_kills():
    parser = KillfeedParser(config=KillfeedConfig(player_names=["SPIDERMAN"]))
    rows = [
        KillfeedRow(timestamp=5.0, actor="HELA", victim="MANTIS", actor_team="enemy"),
        KillfeedRow(timestamp=6.0, actor="HELA", victim="LOKI", actor_team="enemy"),
    ]
    sequence = parser.build_sequence(rows, 0.0, 20.0)

    assert sequence is not None
    assert sequence.attribution_method == "none"
    assert sequence.kill_count == 0
    assert sequence.is_player_attributed is False


def test_evaluate_window_and_batch():
    reader = FakeOCR(
        {
            1.0: [token("SPIDERMAN", 20, 40), token("HELA", 300, 40)],
            2.0: [token("SPIDERMAN", 20, 40), token("LOKI", 300, 40)],
            3.0: [token("SPIDERMAN", 20, 40), token("THOR", 300, 40)],
        }
    )
    parser = KillfeedParser(
        config=KillfeedConfig(player_names=["SPIDERMAN"]),
        ocr_reader=reader,
    )

    frames = [make_frame(ts) for ts in (1.0, 2.0, 3.0)]
    window = WindowROIExtractionResult(
        window_start=0.0,
        window_end=10.0,
        window_duration=10.0,
        frames_by_roi={"kill_feed": frames},
        total_frames=len(frames),
    )

    sequence = parser.evaluate_window(window)
    assert sequence is not None
    assert sequence.kill_count == 3
    assert sequence.multi_kill_label == "TRIPLE KO"

    batch = BatchROIExtractionResult(
        file_path="synthetic.mp4",
        source_width=1920,
        source_height=1080,
        fps=1.5,
        windows_extracted=[window],
        total_frames=len(frames),
    )
    result = parser.evaluate_batch(batch)
    assert result.total_rows == 3
    assert len(result.windows) == 1

    events = killfeed_sequences_to_events(result.windows)
    assert len(events) == 1
    assert events[0].event_type == "triple_ko"
    assert events[0].kill_count == 3
    assert events[0].roi_name == "kill_feed"
    assert events[0].timestamp == 3.0
