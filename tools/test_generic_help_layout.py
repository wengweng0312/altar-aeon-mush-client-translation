"""Regression coverage for generic help, option tables and spellgroup trees."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"


def load_worker():
    spec = importlib.util.spec_from_file_location("generic_help_worker_test", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def render_with_stubs(module, source: str) -> str:
    original_phrase = module.translate_cached_phrase
    original_piece = module.translate_piece
    original_get = module.cache_get
    original_put = module.cache_put
    module.translate_cached_phrase = lambda text, _config: "中譯<%s>" % text
    module.translate_piece = lambda text, _config, **_kwargs: "中譯<%s>" % text
    module.cache_get = lambda _text, _config: None
    module.cache_put = lambda _text, _output, _config: None
    try:
        return module.translate_skill_help_detail(source, {})
    finally:
        module.translate_cached_phrase = original_phrase
        module.translate_piece = original_piece
        module.cache_get = original_get
        module.cache_put = original_put


def main() -> None:
    module = load_worker()

    generic = """Keywords are:  'looking'
Looking is the primary way of obtaining information in this world. You may
look at things, in things, look in directions, look at doors, and all sorts
of other things.
There are also a number of switches that can be added after the look command:
look <character> -condition   Shows you just a character's health.
look <character> -description Shows you just a character's long description.
There are 33 other help pages that may be related to your search.
See 'help search looking' for a list.
See also 'help prompt', 'help spam'."""
    assert module.is_skill_help_detail(generic)
    assert module.should_bypass_whole_block_cache(generic)
    units = module.parse_help_semantic_units(generic)
    assert units[0] == ("help", "Keywords are:  'looking'"), units
    assert sum(kind == "help_option" for kind, _value in units) == 2, units
    assert ("help", "See 'help search looking' for a list.") in units, units
    rendered = render_with_stubs(module, generic)
    rows = rendered.splitlines()
    assert rows[0] == "關鍵詞：'looking'", rows
    assert "look <character> -condition - 中譯<Shows you just a character's health.>" in rows, rows
    assert "列表請參閱 'help search looking'。" in rows, rows
    assert "另請參閱：'help prompt', 'help spam'." in rows, rows
    assert len(rows) >= 8, rows

    spellgroup = """Keywords are:  'spellgroup mage elemental fire'
Mage elemental fire spellgroup:
 shower of sparks                           1 mag
   burning hands                            6 mag
     fire shield                           11 mag
       flame blade                         13 mag
The elemental fire spells are mostly combat spells in nature. They do
not require a great deal of control on the part of the caster."""
    assert module.is_skill_help_detail(spellgroup)
    units = module.parse_help_semantic_units(spellgroup)
    tree_units = [value for kind, value in units if kind == "help_tree"]
    assert len(tree_units) == 4, units
    rendered = render_with_stubs(module, spellgroup)
    rows = rendered.splitlines()
    assert len(rows) == len(units), (rows, units)
    assert any("中譯<shower of sparks>" in row and row.endswith("1 mag") for row in rows), rows
    assert any("中譯<flame blade>" in row and row.endswith("13 mag") for row in rows), rows

    spell = """Keywords are:  'necromancer spell coldfire fire unfire'
Spell: coldfire                 Mana:   6  Int: 13  Wis: 11  Lvl  1 Necr  (42%)
(critical)
Group: Necromancer Spectral Rot
Damage Type: ice
Damage: minor
Speed: average
(Can Be Bloodcast)
Coldfire absorbs heat and light.
You can create the spell 'coldfire' on the following consumables:
Potions   Scrolls"""
    rendered = render_with_stubs(module, spell)
    rows = rendered.splitlines()
    assert "傷害類型：中譯<ice>" in rows, rows
    assert "傷害：中譯<minor>" in rows, rows
    assert "可使用血液施放" in rows, rows
    assert "你可以在以下消耗品上製作 'coldfire'：" in rows, rows

    short_help = """Keywords are:  'autoshort'
The autoshort command allows you to toggle on or off highlighted room short
descriptions."""
    assert module.is_skill_help_detail(short_help)
    rendered = render_with_stubs(module, short_help)
    assert len(rendered.splitlines()) == 2, rendered

    config_help = """Keywords are:  'mush-z mushz config playquotes'
Syntax: 'config playquotes'
Summary: Play death quote voiceovers
Possible Values: Enabled / Disabled"""
    rendered = render_with_stubs(module, config_help)
    assert rendered.splitlines() == [
        "關鍵詞：'mush-z mushz config playquotes'",
        "語法：'config playquotes'",
        "摘要：中譯<Play death quote voiceovers>",
        "可用值：啟用／停用",
    ], rendered

    syntax_help = """Keywords are:  'brag share stats'
Syntax:
brag <information>
brag <channel name> <information>
The brag command shows information about your character."""
    rendered = render_with_stubs(module, syntax_help)
    rows = rendered.splitlines()
    assert rows[1:4] == [
        "語法：", "brag <information>", "brag <channel name> <information>",
    ], rows

    format_help = """Keywords are:  'skill brewing potion'
Skill: brew potion              Lvl 12 Mage  (28%)
(important)
Group: Mage alchemy
Profession
Format:
brew potion inventory
brew potion <object list>
The brew potion skill mixes herbs."""
    rendered = render_with_stubs(module, format_help)
    rows = rendered.splitlines()
    assert "專業技能" in rows and "格式：" in rows, rows
    assert "brew potion inventory" in rows and "brew potion <object list>" in rows, rows

    trade_skill_help = """Keywords are:  'skill crafting forge metallurgy'
Skill: metallurgy               Lvl 10  Any  (85%)
(helpful)
Group: Smiths Guild Trade Skills
Profession
Guild: The Smiths Guild  Rank: Novice
Usage:
forge
forge check
The metallurgy skill is used to smelt ore."""
    rendered = render_with_stubs(module, trade_skill_help)
    rows = rendered.splitlines()
    assert "技能：中譯<metallurgy>；等級：10；職業：不限職業（85%）" in rows, rows
    assert "公會：中譯<The Smiths Guild>；階級：中譯<Novice>" in rows, rows
    assert "forge" in rows and "forge check" in rows, rows

    config_numbered_values = """Keywords are:  'mush-z config shortid'
Syntax: 'config shortid'
Summary: When identifying an object, simplify the information
Possible Values:
1 - Disabled
2 - Output and history
3 - History only"""
    units = module.parse_help_semantic_units(config_numbered_values)
    assert [kind for kind, _value in units].count("help_value_option") == 3, units
    rendered = render_with_stubs(module, config_numbered_values)
    rows = rendered.splitlines()
    assert rows[-4:] == [
        "可用值：", "1 - 中譯<Disabled>", "2 - 中譯<Output and history>",
        "3 - 中譯<History only>",
    ], rows

    terrain_definitions = """Keywords are:  'ocean river stream aquatic biomes'
There are several types of aquatic terrain:
stream     - brooks, creeks, shallow rivers
river      - deep natural watercourses or artificial canals
water      - ponds, lakes, springs
underwater - beneath the surface of deep water
ocean      - saltwater and estuaries
beach      - shorelines of large bodies of water
These terrains require swimming."""
    units = module.parse_help_semantic_units(terrain_definitions)
    assert [kind for kind, _value in units].count("help_table") == 6, units
    rendered = render_with_stubs(module, terrain_definitions)
    rows = rendered.splitlines()
    assert "stream     - 中譯<brooks, creeks, shallow rivers>" in rows, rows
    assert "underwater - 中譯<beneath the surface of deep water>" in rows, rows

    assert module.numeric_items_preserved(
        "Wimp activates at 1/5 of your hitpoints.",
        "膽怯模式會在你的生命值降至五分之一時啟動。",
    )

    deeds_table = """Keywords are:  'deeds'
Complete lists of deeds can be displayed using the following commands:
deeds                   - show a list of deeds you have completed
deeds <player name>     - show a list of deeds another player has completed
deeds sloe              - show a list of deeds on the island of sloe
deeds all               - show a list of all available deeds
For information about quests, use the 'quest help' command."""
    units = module.parse_help_semantic_units(deeds_table)
    assert [kind for kind, _value in units].count("help_table") == 4, units
    rendered = render_with_stubs(module, deeds_table)
    rows = rendered.splitlines()
    assert "deeds <player name>     - 中譯<show a list of deeds another player has completed>" in rows, rows
    assert rows[-1] == "中譯<For information about quests, use the 'quest help' command.>", rows

    channel_table = """Keywords are:  'channel restrictions'
The following public channels are available:
(player defined channels) - player defined channels are the least regulated
channels. The owner may change channel parameters.
auction   - for topics related to buying, selling, and trading.
newbie    - for newbie questions. Be nice on this channel -
            very nice. If you can't be nice, turn it off.
gossip    - for miscellaneous chatting. Listen
            to what the owner has to say.
zt        - for discussions of the mush-z client
Spamming will not be tolerated on any channel."""
    units = module.parse_help_semantic_units(channel_table)
    assert [kind for kind, _value in units].count("help_table") == 5, units
    rendered = render_with_stubs(module, channel_table)
    rows = rendered.splitlines()
    assert "(player defined channels) - 中譯<player defined channels are the least regulated channels. The owner may change channel parameters.>" in rows, rows
    assert "newbie    - 中譯<for newbie questions. Be nice on this channel - very nice. If you can't be nice, turn it off.>" in rows, rows
    assert rows[-1] == "中譯<Spamming will not be tolerated on any channel.>", rows

    demon_table = """Keywords are:  'necromancer skill summon demon familiars'
Advantages given by various demons:
A black, horned demon     - hitpoints, damage resistance
A winged red imp          - move regen, attacks, mana
An azure blue demon       - elemental saves, elemental absorb
An ebony scaled demon     - hp regen, and saving spell, breath, poison
An energetic green demon  - mana regeneration and movement"""
    units = module.parse_help_semantic_units(demon_table)
    assert [kind for kind, _value in units].count("help_table") == 5, units

    dashed_prose = """Keywords are:  'weapons weaponry'
Weapons can be nearly anything - if you can wield it, you can try to use
it as a weapon. Normally you equip swords, axes and staves, but in a pinch
you can wield other things. These are suboptimal choices - the best weapons
are almost always weapons."""
    units = module.parse_help_semantic_units(dashed_prose)
    assert not any(kind == "help_table" for kind, _value in units), units

    autoassist_prose = """Keywords are:  'autoassist assist'
[Experienced players - this behavior is similar to berserk.
WARNING - The autoassist command is not a true autoassist."""
    units = module.parse_help_semantic_units(autoassist_prose)
    assert not any(kind == "help_table" for kind, _value in units), units

    sectioned_commands = """Keywords are:  'boats ships seafaring sailing'
Syntax:
Information and Settings:
ship christen <name> - name your ship
ship show            - view details of the ship you're on

Movement:
sail <direction> [number] - sail in a direction
anchor
This command is used to manage a ship."""
    units = module.parse_help_semantic_units(sectioned_commands)
    assert [kind for kind, _value in units].count("help_table") == 2, units
    assert [kind for kind, _value in units].count("help_command") == 1, units
    assert ("raw", "anchor") in units, units
    rendered = render_with_stubs(module, sectioned_commands)
    rows = rendered.splitlines()
    assert "中譯<Information and Settings:>" in rows, rows
    assert "ship christen <name> - 中譯<name your ship>" in rows, rows
    assert "sail <direction> [number] - 中譯<sail in a direction>" in rows, rows
    assert "anchor" in rows, rows

    colon_commands = """Keywords are:  'set room commands'
Format:
set room stat    : show ownership of room and room statistics
set room create  : create new rooms for your clan
These commands are only available to editors."""
    units = module.parse_help_semantic_units(colon_commands)
    assert [kind for kind, _value in units].count("help_command") == 2, units
    rendered = render_with_stubs(module, colon_commands)
    rows = rendered.splitlines()
    assert "set room stat    : 中譯<show ownership of room and room statistics>" in rows, rows
    assert "set room create  : 中譯<create new rooms for your clan>" in rows, rows

    quoted_syntax = """Keywords are:  'spells magic spellcasting'
Syntax:
cast '<spell name>' target
cast <spell name> target
c <spell abbreviation> target
Spell names may be abbreviated."""
    units = module.parse_help_semantic_units(quoted_syntax)
    assert [value for kind, value in units if kind == "raw"] == [
        "cast '<spell name>' target", "cast <spell name> target", "c <spell abbreviation> target",
    ], units

    getput_syntax = """Keywords are:  'advanced getput examples get put'
Syntax:
get <name1 name2 name3..>
get all.<type> [container]
put all <container> ground -force
Keywords:
inv or inventory"""
    units = module.parse_help_semantic_units(getput_syntax)
    assert [value for kind, value in units if kind == "raw"] == [
        "get <name1 name2 name3..>", "get all.<type> [container]", "put all <container> ground -force",
    ], units
    assert ("translate", "Keywords:") in units, units

    wrapped_list = """Keywords are:  'train microlevels'
Some facts about microlevels:
- One practice is given on every third microlevel, in addition to the 5
  you receive for the final level.
- You don't lose microlevels when you die."""
    units = module.parse_help_semantic_units(wrapped_list)
    list_rows = [value for kind, value in units if kind == "help_list"]
    assert list_rows == [
        "- One practice is given on every third microlevel, in addition to the 5 you receive for the final level.",
        "- You don't lose microlevels when you die.",
    ], units

    board_example = """Keywords are:  'boards message delete deletion'
Format:
remove <message #> board
remove <message #> <board name>
For example,
remove 13 board
You may remove messages addressed to you."""
    units = module.parse_help_semantic_units(board_example)
    assert ("translate", "For example,") in units, units
    assert ("raw", "remove 13 board") in units, units

    wrapped_format_prose = """Keywords are:  'train microlevels'
Format:
For levels that would cost more than about 11 million experience each, the
game breaks those levels up into micro-levels with smaller requirements."""
    units = module.parse_help_semantic_units(wrapped_format_prose)
    assert not any(kind == "raw" for kind, _value in units), units
    assert units[-1][0] == "translate" and "game breaks" in units[-1][1], units

    prompt_tags = """Keywords are:  'prompts noprompt'
Regular tags you can use in your prompt:
%hp      hitpoints
%name    insult string
%%       a single %"""
    units = module.parse_help_semantic_units(prompt_tags)
    assert [kind for kind, _value in units].count("help_tag") == 3, units
    rendered = render_with_stubs(module, prompt_tags)
    rows = rendered.splitlines()
    assert "%hp      中譯<hitpoints>" in rows, rows
    assert "%%       中譯<a single %>" in rows, rows

    listed_help = """Keywords are:  'daily gifts'
Gifts include:
 - experience
 - gold
 - bank remote access time"""
    rendered = render_with_stubs(module, listed_help)
    rows = rendered.splitlines()
    assert rows[-3:] == [
        " - 中譯<experience>",
        " - 中譯<gold>",
        " - 中譯<bank remote access time>",
    ], rows

    timeout_help = """Keywords are:  'character delete deletion'
The timeout is based on level:
 - 12 months for a level  1, all levels   1 char
 - 64 months for a level 30, all levels 104 char"""
    rendered = render_with_stubs(module, timeout_help)
    rows = rendered.splitlines()
    assert rows[-2:] == [
        " - 等級 1、總等級 1 的角色：12 個月",
        " - 等級 30、總等級 104 的角色：64 個月",
    ], rows

    print("GENERIC_HELP_LAYOUT_OK generic=yes short=yes config=yes syntax=yes format=yes command-sections=yes lists=yes spellgroup=4 cache=bypass")


if __name__ == "__main__":
    main()
