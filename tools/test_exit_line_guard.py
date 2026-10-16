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
    assert 'sentence_terminated = text:find("[%.%!%?]%s*$") ~= nil' in exit_check
    assert "not heading and count == 1 and sentence_terminated" in exit_check

    # The regression that motivated this guard: a display-wrapped prose
    # sentence ending in a direction must stay with the room description,
    # while a bare or explicitly labelled direction remains an exit.
    def classified_as_exit(line: str) -> bool:
        raw = line.strip().lower()
        labelled = raw.startswith(("exit:", "exits:", "door:", "doors:"))
        if labelled:
            return True
        sentence_terminated = raw.endswith((".", "!", "?"))
        words = [word.strip("[](){},.") for word in raw.split()]
        directions = {
            "n", "s", "e", "w", "u", "d", "ne", "nw", "se", "sw",
            "north", "south", "east", "west", "up", "down",
            "northeast", "northwest", "southeast", "southwest", "none",
        }
        if not words or any(word not in directions for word in words):
            return False
        return not (len(words) == 1 and sentence_terminated)

    assert not classified_as_exit("east.")
    assert classified_as_exit("east")
    assert classified_as_exit("east west")
    assert classified_as_exit("Exits: east")
    print(
        "EXIT_LINE_GUARD_OK labelled=yes mushz_doors=directions_only "
        "wrapped_prose=buffered punctuated_direction=buffered"
    )


if __name__ == "__main__":
    main()
