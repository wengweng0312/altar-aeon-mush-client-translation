"""Guard against treating display-wrapped room prose as a door heading."""

from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "src/mush-z/worlds/plugins/Translation_Mode.xml"


def main() -> None:
    ET.parse(PLUGIN)
    source = PLUGIN.read_text(encoding="utf-8")
    section = source.split("local function strip_exit_heading", 1)[1].split(
        "local function is_exit_line", 1
    )[0]
    assert '"^door%s*:%s*"' in section
    assert '"^doors%s*:%s*"' in section
    assert '{"^doors%s+", "door", true}' in section
    assert '"^door%s+"' not in section
    exit_check = source.split("local function is_exit_line", 1)[1].split(
        "local exit_labels", 1
    )[0]
    assert "heading and not directions_only" in exit_check
    assert "if not exit_words[word] then return false end" in exit_check
    print(
        "EXIT_LINE_GUARD_OK labelled=yes mushz_doors=directions_only "
        "wrapped_prose=buffered"
    )


if __name__ == "__main__":
    main()
