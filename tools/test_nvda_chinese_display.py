"""Regression tests for the provider-neutral Chinese MUD review layer."""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "src" / "nvda-addon" / "appModules" / "mushclient.py"
FUNCTIONS = {
    "_isCJK",
    "_cleanEnglishKey",
    "_cleanLandmarkKey",
    "_cleanFixtureSubject",
    "_addEnglishKey",
    "_safeEntityKey",
    "_englishRoomTitleIndex",
    "_isDirectionalActorMovement",
    "_translationEnglishKeys",
    "_splitMergedChineseRoomTitle",
	"_translationPairedRoomLines",
    "_translationPairedProseLines",
    "_translationChinesePresentationLines",
    "_translationPairedDialogueLines",
    "_isStructuredTranslationReview",
    "_translationReviewMetadata",
    "_translationReviewPresentation",
    "_translationPresentationChineseStart",
    "_translationPresentationSegments",
    "_translationPresentationInitialOffset",
    "_translationPresentationLineRanges",
    "_translationOriginalEnglish",
}


def load_display_functions() -> dict[str, object]:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    body = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id.startswith("_") for target in targets):
                body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
            body.append(node)
    namespace = {"re": re}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(MODULE), "exec"), namespace)
    return namespace


def main() -> None:
    module = load_display_functions()
    extract = module["_translationEnglishKeys"]
    present = module["_translationReviewPresentation"]
    original = module["_translationOriginalEnglish"]

    cases = (
        ("Pikan says, 'Bring this letter to Fast Eddie in the Dragon Tooth research guild.'", {"Pikan", "Fast Eddie", "Dragon Tooth research guild"}),
        ("Some fungal ooze", {"fungal ooze"}),
        ("The sword of the Tyranids (unique) (hum)", {"sword of the Tyranids"}),
        ("You put a leather satchel in a battered oak chest.", {"leather satchel", "battered oak chest"}),
        ("You get a silver key from the corpse of Old Grub.", {"silver key", "corpse of Old Grub"}),
        ("Once inside the forest, use the 'nearby' command to find the Trogdolyte caves.", {"nearby", "Trogdolyte caves"}),
        ("Complete tasks for a reward! Use 'task list' for details.", {"task list"}),
        ("A dwarven sentinel leaves east.", set()),
        ("A tyranid gargoyle flies south.", set()),
        ("Icy flies northwest.", set()),
        ("A small spider crawls toward the north.", set()),
        ("A mounted guard rides off southeast.", set()),
        ("A sturdy sentinel patrols the town of Dragon Tooth.", {"sturdy sentinel"}),
        ("A panting dwarf stands here, catching his breath.", {"panting dwarf"}),
        ("A short wooden sign has been stuck in the ground with directions.", {"short wooden sign"}),
        ("A large bulletin board is hovering above the ground here.", {"large bulletin board"}),
        ("A fallen boulder on the side of the ledge is covered in moss.", {"fallen boulder"}),
        ("Halfway up, a small hole can be appreciated from the west.", {"small hole"}),
        ("A large natural pillar occupies this part of the chamber.", {"large natural pillar"}),
        ("Rocks jut up from the ground along both sides of the street.", {"Rocks"}),
        ("There is a ladder leading down into the darkness.", {"ladder"}),
        ("locksmithing 84%", {"locksmithing"}),
    )
    for source, expected in cases:
        actual = set(extract(source))
        missing = expected - actual
        assert not missing, (source, missing, actual)
        if source == "A sturdy sentinel patrols the town of Dragon Tooth.":
            assert "Dragon Tooth" not in actual, actual
        if source == "A dwarven sentinel leaves east.":
            assert not actual, actual

    actor_movement = module["_isDirectionalActorMovement"]
    assert actor_movement("A tyranid gargoyle flies south.")
    assert actor_movement("A small spider crawls toward the north.")
    assert not actor_movement("The path heads north.")
    assert not actor_movement("The main road runs east.")
    assert not actor_movement("You follow Icy northwest.")

    english = (
        "Dragon Tooth way\n"
        "Following the dusty path through the town, plenty of movement can be seen\n"
        "around. Dwarves walking around, axe in hand, they don't look particularly\n"
        "willing to speak to anybody."
    )
    chinese = (
        "龍牙之道\n"
        "沿著鎮上塵土飛揚的小徑走，可以看到許多動靜\n"
        "四處走動。矮人們手持斧頭在四處走動，看起來並不特別\n"
        "願意與任何人交談。"
    )
    bilingual = chinese + " | " + english
    shown = present(bilingual)
    lines = shown.splitlines()
    assert len(lines) == 1, lines
    assert lines[0].startswith("龍牙之道 沿著鎮上塵土飛揚的小徑走"), lines
    assert " | Dragon Tooth way Following the dusty path" in lines[0], lines
    assert lines[0].endswith("willing to speak to anybody."), lines
    assert original(bilingual) == english

    merged = (
        "龍牙之路繼續以東西走向延伸，周圍有許多矮人巡邏。"
        "西北方向可以看到一個巨大的傳送門。 | "
        "Dragon Tooth way\nThe path continues west-east. A huge portal is northwest."
    )
    merged_lines = present(merged).splitlines()
    assert len(merged_lines) == 1, merged_lines
    assert merged_lines[0].startswith("龍牙之路繼續以東西走向延伸"), merged_lines
    assert merged_lines[0].endswith("A huge portal is northwest."), merged_lines

    segments_for = module["_translationPresentationSegments"]
    mixed = "一個喘著氣的矮人站在這裡，喘著氣。\n〔panting dwarf〕"
    segments = [mixed[start:end] for start, end in segments_for(mixed)]
    assert segments == ["一個喘著氣的矮人站在這裡，", "喘著氣。", "panting", "dwarf"], segments
    title_mixed = "龍牙之路〔Dragon Tooth way〕\n道路向東延伸。"
    title_segments = [title_mixed[start:end] for start, end in segments_for(title_mixed)]
    assert title_segments == ["龍牙之路", "Dragon", "Tooth", "way", "道路向東延伸。"], title_segments
    assert module["_translationPresentationInitialOffset"](mixed) == 0

    prefixed_english = (
        "Your next cheapest level is a tie for 12000000\n"
        "Dragon Tooth way\n"
        "The path continues in a west-east fashion, with plenty of dwarven circulating."
    )
    prefixed_chinese = (
        "你下一個最便宜的等級有多個並列，費用為 12000000。\n"
        "龍牙之道\n"
        "這條路繼續呈西向東走向，許多矮人在巡迴。"
    )
    prefixed_lines = present(prefixed_chinese + " | " + prefixed_english).splitlines()
    assert len(prefixed_lines) == 3, prefixed_lines
    assert prefixed_lines[0].endswith("Your next cheapest level is a tie for 12000000"), prefixed_lines
    assert prefixed_lines[1] == "龍牙之道 | Dragon Tooth way", prefixed_lines
    line_text = "龍牙之路〔Dragon Tooth way〕\n繼續以東西走向延伸。\n〔huge portal〕"
    line_ranges = module["_translationPresentationLineRanges"](line_text)
    assert [line_text[start:end] for start, end in line_ranges] == [
        "龍牙之路〔Dragon Tooth way〕",
        "繼續以東西走向延伸。",
        "〔huge portal〕",
    ]
    quoted = module["_translationChinesePresentationLines"](
        "門上寫著你會把信帶過去嗎？”現在就走吧。』",
        "The sign asks whether you will take the letter. Now leave.",
    )
    assert quoted == ["門上寫著你會把信帶過去嗎？”", "現在就走吧。』"], quoted

    same_line = "一個喘著氣的矮人站在這裡，喘著氣。 | A panting dwarf stands here, catching his breath."
    same_line_segments = [same_line[start:end] for start, end in segments_for(same_line)]
    assert same_line_segments[:2] == ["一個喘著氣的矮人站在這裡，", "喘著氣。"], same_line_segments
    assert same_line_segments[2:5] == ["A", "panting", "dwarf"], same_line_segments
    assert module["_isStructuredTranslationReview"]("Quest Name: Find the mushroom")
    assert module["_isStructuredTranslationReview"]("spell knowledge 6 -- -- 100%")
    assert not module["_isStructuredTranslationReview"]("A short wooden sign is here.")
    quest_marked = "\x1eTMREVIEW:quest\x1e任務概述： | General Quest Info:"
    assert "TMREVIEW" not in present(quest_marked)
    assert present(quest_marked) == "任務概述： | General Quest Info:"
    assert original(quest_marked) == "General Quest Info:"
    quest_prose_marked = "\x1eTMREVIEW:quest\x1e請尋求更多資訊。 | Seek him out for more information."
    assert present(quest_prose_marked) == "請尋求更多資訊。 | Seek him out for more information."
    general_prose = "請尋求更多資訊。 | Seek him out for more information."
    assert present(general_prose) == general_prose
    job_marked = "\x1eTMREVIEW:job\x1e目前接受的工作： | Currently accepted jobs:"
    assert "TMREVIEW" not in present(job_marked)
    assert present(job_marked) == "目前接受的工作： | Currently accepted jobs:"
    assert original(job_marked) == "Currently accepted jobs:"

	# Long NPC speech is split only when both languages have the same safe
	# sentence count. It remains one history entry, with one bilingual row per
	# sentence for numpad 7/9 review.
    ceska = (
        "剝皮匠切斯卡說：「我剝動物皮，群獵。我做衣服，還有盔甲。"
        "我經常用森林動物的皮，但我會覺得無聊。想和異國野獸的皮合作。"
        "你帶給我新的皮，我做點東西給你。」 | "
        "Ceska the skinner says, 'I skin animals the pack hunts. I make clothing and armor. "
        "I work with hide from forest animals all the time, but I get bored. "
        "Want to work with hide of an exotic beast. You bring me a new hide and I make something for you.'"
    )
    ceska_lines = present(ceska).splitlines()
    assert len(ceska_lines) == 5, ceska_lines
    assert ceska_lines[0].startswith("剝皮匠切斯卡說"), ceska_lines
    assert ceska_lines[0].endswith("I skin animals the pack hunts."), ceska_lines
    assert ceska_lines[-1].endswith("I make something for you.'"), ceska_lines

    voiced_dialogue = (
        "Dractoz Clawheart 用惱怒的語氣說：「入侵我們的領地，還想讓我們殺了你。"
        "仙子們已經越界了。我想是時候有人跟女王們談談了。"
        "女王們住在森林裡的堡壘裡，中央橋以西。"
        "Kindri 女士是最年輕的女王，也可能是最安全的起點。"
        "仙女法律禁止走私，所以你有情報可以提供。讓他們別再煩我們了。」 | "
        "Dractoz Clawheart says in an irritated voice, 'Invading our territory, and trying to make us kill you. "
        "The fairies have crossed lines. I think it is time someone talks to the Queens. "
        "Queens live in a fortress in the forest, west of the central bridge. "
        "Lady Kindri is the youngest Queen and probably safest to start with. "
        "Smuggling is not allowed by fairy laws, so you have information to offer. "
        "Make them stop bothering us.'"
    )
    voiced_lines = present(voiced_dialogue).splitlines()
    assert len(voiced_lines) == 7, voiced_lines
    assert voiced_lines[0].endswith("trying to make us kill you."), voiced_lines
    assert voiced_lines[-1].endswith("Make them stop bothering us.'"), voiced_lines

    cellar = (
        "你沿著陡峭的臺階走進黑暗之中。\n"
        "酒窖\n"
        "這是一間堆滿桶子和箱子的陰暗潮濕酒窖。\n"
        "沿著一面牆，稻草被鋪成床，角落水桶散發出難聞氣味。 | "
        "You make your way down the steep steps into the gloom.\n"
        "Cellar\n"
        "A dark and damp cellar filled with barrels and crates. Along one wall a\n"
        "pile of straw has been fashioned into a bed and there is an unpleasant aroma."
    )
    cellar_lines = present(cellar).splitlines()
    assert len(cellar_lines) == 4, cellar_lines
    assert cellar_lines[0].endswith("You make your way down the steep steps into the gloom."), cellar_lines
    assert cellar_lines[1] == "酒窖 | Cellar", cellar_lines
    assert cellar_lines[-1].endswith("there is an unpleasant aroma."), cellar_lines

    hawkins = (
        "你將一個裝滿綠色粘液的樣品罐交給霍金斯，煉金術士。"
        "霍金斯用長金屬鉗子接過罐子，並放在工作臺上。"
        "『這正是我需要的。我想出了穩定釀造過程的方法。"
        "我需要一些石灰藻類。我知道朋友維格會有。"
        "他是龍牙城的藥劑師。你能去和他談談嗎？"
        "他一定會提供藻類。請快點，時間至關重要。』 | "
        "You give a sample jar full of green slime to Hawkins, the alchemist. "
        "Hawkins takes the jar with long metal tongs and puts it on his workbench. "
        "'This is just what I need. I worked out how to stabilise the brew. "
        "I need some limestone algae. I know my friend Vig will have some. "
        "He is a herbalist in Dragontooth. Could you go and talk with him please? "
        "He will provide some algae. Please hurry, time is of the essence.'"
    )
    hawkins_lines = present(hawkins).splitlines()
    assert len(hawkins_lines) == 10, hawkins_lines
    assert hawkins_lines[0].startswith("你將一個裝滿綠色粘液的樣品罐"), hawkins_lines
    assert hawkins_lines[-1].endswith("Please hurry, time is of the essence.'"), hawkins_lines

    mismatched_dialogue = "守衛說：「快走。現在！」 | A guard says, 'Leave now.'"
    assert present(mismatched_dialogue) == mismatched_dialogue

    addon_source = MODULE.read_text(encoding="utf-8")
    navigator_method = addon_source.split("\tdef setNavigator(self):", 1)[1].split("\n\n\nclass AppModule", 1)[0]
    assert "currentNavigator = api.getNavigatorObject()" in navigator_method
    assert "_translationReviewIsActive()" in navigator_method
    assert "isinstance(currentNavigator, TranslationReviewObject)" in navigator_method
    assert navigator_method.index("isinstance(currentNavigator, TranslationReviewObject)") < navigator_method.index("api.setNavigatorObject(output)")
    bottom_script = addon_source.split("def script_translationHistoryBottom", 1)[1].split("\n\t@", 1)[0]
    assert "_syncTranslationReviewPosition(True, atEnd=True)" in bottom_script

    print("NVDA_CHINESE_DISPLAY_OK safe_dialogue_pairing=yes structured_translation_preserved=yes")


if __name__ == "__main__":
    main()
