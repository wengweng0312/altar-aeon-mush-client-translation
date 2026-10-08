"""The pre-character welcome must translate without a model or cloud API."""

from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"
module = runpy.run_path(str(WORKER), run_name="character_creation_welcome_test")

source = """Welcome to Alter Aeon, a fantasy adventure game set in a world
of swords and sorcery, magic and dragons!
If you already have a character, enter the name now.
If you are new, you must create and name a new character.
Would you like to create a new character?  """

assert module["is_character_creation_welcome"](source)
translated = module["translate_character_creation_welcome"](source)
rows = translated.splitlines()
assert len(rows) == 5
assert rows[0].startswith("歡迎來到 Alter Aeon")
assert rows[1] == "充滿刀劍、巫術、魔法與巨龍！"
assert rows[-1] == "你想建立新角色嗎？"
assert module["should_bypass_whole_block_cache"](source)

# The fixed translator must preserve an unknown line instead of dropping it.
variant = source + "\nUnrecognized server notice."
variant_rows = module["translate_character_creation_welcome"](variant).splitlines()
assert variant_rows[-1] == "Unrecognized server notice."

print("character creation welcome regression: PASS")
