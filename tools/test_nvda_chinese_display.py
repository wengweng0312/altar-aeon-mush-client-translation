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
    "_translationPairedMonsterLoreLines",
    "_translationTaskListLines",
    "_translationPairedTaskListLines",
    "_translationPairedSalesLines",
    "_translationPairedSyntaxLines",
    "_translationPairedProseLines",
    "_isHelpUsageCommand",
    "_translationHelpSemanticLines",
    "_translationPairedHelpLines",
    "_translationCommandUsageLines",
    "_translationPairedCommandUsageLines",
    "_translationNewsSemanticLines",
    "_translationPairedNewsLines",
    "_translationChangesSemanticLines",
    "_translationPairedChangesLines",
    "_translationChinesePresentationLines",
    "_translationPairedDialogueLines",
    "_isStructuredTranslationReview",
    "_boundedReviewChunks",
    "_boundedBilingualFallback",
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

    helpEnglish = (
        "Keywords are:  'cleric spell breath of life'\n"
        "Spell: breath of life           Mana:  25  Wis: 32  Chr: 28  Lvl 31 Cler  (28%)\n"
        "                                (important)   Requires: major heal\n"
        "                                Group: Cleric healing spellgroup\n"
        "Usage:\n"
        "cast breath of life <character>\n"
        "This very powerful healing spell can be used on seriously injured targets,\n"
        "and can sometimes heal the injured completely in one cast.\n"
        "It generally cannot be cast on targets with only minor injuries."
    )
    helpChinese = (
        "關鍵詞：'cleric spell breath of life'\n"
        "咒語：生命氣息；法力：25；智慧：32；魅力：28；等級：31；職業：牧師（28%）\n"
        "重要；前置需求：強效治療\n"
        "分組：牧師治療法術組\n"
        "用法：\n"
        "cast breath of life <character>\n"
        "這個強大的治療咒語可用於重傷目標，有時能一次完全治癒傷者。\n"
        "它通常不能對僅受輕傷的目標施放。"
    )
    helpLines = present(helpChinese + " | " + helpEnglish).splitlines()
    assert len(helpLines) == 8, helpLines
    assert helpLines[1].endswith("Lvl 31 Cler  (28%)"), helpLines
    assert helpLines[5] == "cast breath of life <character> | cast breath of life <character>", helpLines
    assert helpLines[-1].endswith("It generally cannot be cast on targets with only minor injuries."), helpLines

    generic_help_english = (
        "Showing page 1.\n"
        "Keywords are: 'reboots resets repops'\n"
        "A reboot restarts the mud.\n"
        "There are 11 other help pages related to your search.\n"
        "See 'help search reboot' for a list."
    )
    generic_help_chinese = (
        "顯示第 1 頁。\n"
        "關鍵詞：'reboots resets repops'\n"
        "重新啟動會重啟 MUD。\n"
        "還有 11 個其他相關說明頁面。\n"
        "請使用 'help search reboot' 查看清單。"
    )
    generic_help_lines = present(generic_help_chinese + " | " + generic_help_english).splitlines()
    assert len(generic_help_lines) == 5, generic_help_lines
    assert generic_help_lines[0].endswith("Showing page 1."), generic_help_lines
    assert generic_help_lines[-1].endswith("See 'help search reboot' for a list."), generic_help_lines

    preservation_english = (
        "Keywords are: 'necromancer spell preservation preserve'\n"
        "Spell: preservation Mana: 16 Int: 18 Wis: 16 Lvl 10 Necr (28%)\n"
        "(important) Requires: undead lore\nGroup: Necromancer Undead Skills\nUsage:\n"
        "cast preservation <object>\n"
        "The spell slows the decay of corpses and other organic matter.\n"
        "Note that it will not work on inorganic materials,\n"
        "but it prolongs the shelf life of food.\n"
        "You can create the spell 'preservation' on the following consumables:\n"
        "Potions Scrolls Spellstaffs"
    )
    preservation_chinese = (
        "關鍵詞：'necromancer spell preservation preserve'\n"
        "咒語：保存；法力：16；智力：18；智慧：16；等級：10；職業：死靈法師（28%）\n"
        "重要；前置需求：不死傳說\n分組：死靈法師技能\n用法：\n"
        "cast preservation <object>\n防腐術會減緩屍體腐爛。\n"
        "請注意，它對無機材料不起作用，但可延長食物保存期。\n"
        "你可以在以下消耗品上製作 'preservation'：\n藥劑、卷軸、法杖"
    )
    preservation_lines = present(preservation_chinese + " | " + preservation_english).splitlines()
    assert len(preservation_lines) == 10, preservation_lines
    assert preservation_lines[7].endswith("but it prolongs the shelf life of food."), preservation_lines
    assert preservation_lines[-1].endswith("Potions Scrolls Spellstaffs"), preservation_lines

    treasure_english = (
        "Keywords are: 'treasure bullion ingots billets'\n"
        "While shopping, you may find items that are type TREASURE.\n"
        "These can sometimes be used as raw material for forging."
    )
    treasure_chinese = (
        "關鍵詞：'treasure bullion ingots billets'\n"
        "購物時，你可能找到寶藏類物品。\n"
        "這些物品有時可作為鍛造原料。"
    )
    treasure_lines = present(treasure_chinese + " | " + treasure_english).splitlines()
    assert len(treasure_lines) == 3, treasure_lines
    assert all(" | " in row for row in treasure_lines), treasure_lines

    spellgroup_english = (
        "Keywords are: 'spellgroup warrior iron body skillgroup'\n"
        "Warrior iron body:\n"
        "increased stamina                         13 war\n"
        "armored skin                             28 war\n"
        "second wind                              22 war\n"
        "indomitable will                         37 war\n"
        "last stand                               38 war\n"
        "iron claw                                25 war\n"
        "These skills improve physical resistance, and allow exhausted fighters\n"
        "to sometimes surpass their physical limits."
    )
    spellgroup_chinese = (
        "關鍵詞：'spellgroup warrior iron body skillgroup'\n戰士鐵體：\n"
        "增加耐力 13 war\n盔甲皮膚 28 war\n第二春 22 war\n"
        "不屈的意志 37 war\n堅守陣地 38 war\n鐵爪 25 war\n"
        "這些技能提高身體抵抗力，讓疲憊的戰士超越體力極限。"
    )
    spellgroup_lines = present(spellgroup_chinese + " | " + spellgroup_english).splitlines()
    assert len(spellgroup_lines) == 9, spellgroup_lines
    assert spellgroup_lines[2].endswith("increased stamina                         13 war"), spellgroup_lines
    assert spellgroup_lines[-1].endswith("to sometimes surpass their physical limits."), spellgroup_lines

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

    nearby_english = (
        "There are the following unfinished quests nearby:\n"
        "Num  Level  Name\n"
        "  1     27  Free a special mushroom for an alchemist.\n"
        "  2     28  Give a troll a chance.\n"
        "For details on a quest, use 'quest nearby'. For example, 'quest nearby 1'."
    )
    nearby_chinese = (
        "附近有以下尚未完成的任務：\n"
        "編號　等級　名稱\n"
        "  1　27　為煉金術士釋放一種特殊蘑菇。\n"
        "  2　28　給巨魔一次機會。\n"
        "若要查看任務詳情，請使用 quest nearby，例如 quest nearby 1。"
    )
    nearby_lines = present(nearby_chinese + " | " + nearby_english).splitlines()
    assert len(nearby_lines) == 5, nearby_lines
    assert nearby_lines[0].endswith("There are the following unfinished quests nearby:"), nearby_lines
    assert nearby_lines[2].endswith("Free a special mushroom for an alchemist."), nearby_lines
    assert nearby_lines[3].endswith("Give a troll a chance."), nearby_lines
    assert nearby_lines[-1].endswith("For example, 'quest nearby 1'."), nearby_lines

    sales_english = (
        "There are the following sales running:\n"
        " 5% extra! - weightless expansions\n"
        "40% off! - detect and protect spells - now 15 credits!\n"
        "Use the 'credit buy' command to take advantage of these deals."
    )
    sales_chinese = (
        "目前有以下促銷活動：\n"
        "額外 5%！- 無重量擴充\n"
        "優惠 40%！- 偵測與防護法術 - 現在 15 credits！\n"
        "請使用 'credit buy' 指令購買這些優惠。"
    )
    sales_lines = present(sales_chinese + " | " + sales_english).splitlines()
    assert len(sales_lines) == 4, sales_lines
    assert sales_lines[1].endswith("5% extra! - weightless expansions"), sales_lines
    assert sales_lines[2].endswith("40% off! - detect and protect spells - now 15 credits!"), sales_lines

    syntax_english = (
        "Syntax:\n"
        "friends - show logged in friends and recent activity\n"
        "friend replay [name] - see what your friends have done recently\n"
        "What do you want to do with your friends list?"
    )
    syntax_chinese = (
        "語法：\n"
        "friends - 顯示已登入的朋友與近期活動\n"
        "friend replay [name] - 查看朋友最近做過什麼\n"
        "你想如何處理朋友清單？"
    )
    syntax_lines = present(syntax_chinese + " | " + syntax_english).splitlines()
    assert len(syntax_lines) == 4, syntax_lines
    assert syntax_lines[1].endswith("friends - show logged in friends and recent activity"), syntax_lines
    assert syntax_lines[2].endswith("friend replay [name] - see what your friends have done recently"), syntax_lines

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

    monster_lore = (
        "這是一個 0。\n"
        "完美搭配！不要連續兩次嘗試……\n"
        "你的盔甲無法抵擋狗頭人戰爭領袖的攻擊。\n"
        "你運用了關於怪物知識：一名狗頭人戰爭領袖……\n"
        "可能對火比較敏感。 | "
        "it's a 0.\n"
        "The perfect match! Don't try it twice in a row...\n"
        "Your armor would be no defense against A kobold war leader's attacks.\n"
        "You use your knowledge of monster lore:\n"
        "A kobold war leader...\n"
        "Might be somewhat vulnerable to fire."
    )
    monster_lore_lines = present(monster_lore).splitlines()
    assert len(monster_lore_lines) == 6, monster_lore_lines
    assert monster_lore_lines[3].endswith("You use your knowledge of monster lore:"), monster_lore_lines
    assert monster_lore_lines[4].endswith("A kobold war leader..."), monster_lore_lines

    mismatched_dialogue = "守衛說：「快走。現在！」 | A guard says, 'Leave now.'"
    assert present(mismatched_dialogue) == mismatched_dialogue

    period_room_english = (
        "At the base of a large tree.\n"
        "You're at the base of a huge tree. Looking up it seems to go up forever, almost\n"
        "like one of those giant sequoia trees you've read about in your science\n"
        "books. You feel, for a moment, like you're standing next to living history,\n"
        "but then your adventurous nature takes over, and you simply have to climb it!\n"
        "A flying bit of fluff just dive-bombed you!"
    )
    period_room_chinese = (
        "在一棵大樹的樹根旁。\n"
        "你站在一棵大樹的底部。\n"
        "看起來像是永遠向上生長，幾乎就像你在科學書中讀到的那些巨大的紅杉樹一樣。\n"
        "你會覺得，有一瞬間你站在了活生生的歷史旁邊，但隨後你的冒險天性就會占據主導地位，你就不得不爬上去！\n"
        "一隻飛舞的毛絨小東西剛剛向你投擲了一枚炸彈！"
    )
    assert module["_englishRoomTitleIndex"](period_room_english.splitlines()) == 0
    period_room_lines = present(period_room_chinese + " | " + period_room_english).splitlines()
    assert len(period_room_lines) == 5, period_room_lines
    assert period_room_lines[0].endswith("At the base of a large tree."), period_room_lines
    assert period_room_lines[1].endswith("You're at the base of a huge tree."), period_room_lines
    assert period_room_lines[-1].endswith("A flying bit of fluff just dive-bombed you!"), period_room_lines

    huge_fallback = (("很長的未分類內容，" * 90) + " | " + ("unknown structured output " * 90)).strip()
    huge_lines = present(huge_fallback).splitlines()
    assert len(huge_lines) >= 3, len(huge_lines)
    assert max(map(len, huge_lines)) <= 1250, max(map(len, huge_lines))

    news_chinese = """ALTER AEON 新聞
今日頭條：
任務在再次重啟之前無法運作，問題已經找到。
萬聖節快樂！尋找可雕刻的南瓜！
Alter Aeon 上次重啟時間：Sat Oct 3 17:58:32 2026
（輸入 changes 查看近期更新。）
活動：Shadowheart，等級 60。
今日漁獲：a wahoo，127 磅；捕獲者：Ozhka
新增與近期更新區域：
日期，等級，座標，名稱，創作者
Aug 26 2026，Lvl 27，座標 -3929、56，泰拉尼德洞穴，創作者：alf
Jul 29 2026，Lvl 32，座標 -32、-409，一座廢棄城堡，創作者：bloodlust
Jul 14 2026，Tot 189，座標 -526、561，西海岸，創作者：morpheus"""
    news_english = """ALTER AEON NEWS
TODAY'S HEADLINE:
The quest is not going to work until we get another
reboot, but the problem has been found.
Happy Halloween! Watch for carveable pumpkins when foraging!
Alter Aeon was last booted: Sat Oct 3 17:58:32 2026
(Type 'changes' to see recent updates.)
Got Their Freak On: Shadowheart, level: 60.
Catch of the Day: a wahoo, 127 lbs. - caught by Ozhka
New and recently updated areas:
Date Level [X, Y] Name Creators
Aug 26 2026 Lvl 27 [-3929, 56] Tyranid caves alf
Jul 29 2026 Lvl 32 [-32, -409] An Abandoned Citadel bloodlust
Jul 14 2026 Tot 189 [-526, 561] The Cirustal Coast morpheus"""
    news_lines = present(news_chinese + " | " + news_english).splitlines()
    assert len(news_lines) == 13, news_lines
    assert news_lines[2].endswith("The quest is not going to work until we get another reboot, but the problem has been found."), news_lines[2]
    assert news_lines[-1].endswith("The Cirustal Coast morpheus"), news_lines[-1]

    changes_english = """[3413] ---- Sep 20, 26
From Draak:
Add 'help' option to the scan command.
Casting detect poison before using remove poison on
them makes the curative effect stronger. (Morpheus)
Mobs should no longer bleed to death. Keep in
mind they may still be fragile. (Simo)
Non-aggressive animals should now be more receptive to
being touched.
Most recent 1 entries displayed."""
    changes_chinese = """[3413] ---- Sep 20, 26
來自 Draak：
新增 help 選項。
先偵測毒素會增強治療效果。（Morpheus）
怪物不再因流血死亡。（Simo）
非攻擊性動物更能接受觸摸。
目前顯示最近 1 筆更新。"""
    changes_lines = present(changes_chinese + " | " + changes_english).splitlines()
    assert len(changes_lines) == 7, changes_lines
    assert changes_lines[3].endswith("them makes the curative effect stronger. (Morpheus)"), changes_lines[3]
    assert changes_lines[4].endswith("mind they may still be fragile. (Simo)"), changes_lines[4]

    usage_english = """Usage:
scan help            - this page
scan                 - scan in all directions
scan [direction]     - scan only in the designated direction
scan -dclient [args] - look before scanning"""
    usage_chinese = """用法：
scan help - 此頁面
scan - 向所有方向掃描
scan [direction] - 只向指定方向掃描
scan -dclient [args] - 掃描前查看"""
    usage_lines = present(usage_chinese + " | " + usage_english).splitlines()
    assert len(usage_lines) == 5, usage_lines
    assert usage_lines[0] == "用法： | Usage:", usage_lines
    assert usage_lines[-1].endswith("scan -dclient [args] - look before scanning"), usage_lines

    addon_source = MODULE.read_text(encoding="utf-8")
    navigator_method = addon_source.split("\tdef setNavigator(self):", 1)[1].split("\n\n\nclass AppModule", 1)[0]
    assert "currentNavigator = api.getNavigatorObject()" in navigator_method
    assert "_translationReviewIsActive()" in navigator_method
    assert "isinstance(currentNavigator, TranslationReviewObject)" in navigator_method
    assert navigator_method.index("isinstance(currentNavigator, TranslationReviewObject)") < navigator_method.index("api.setNavigatorObject(output)")
    bottom_script = addon_source.split("def script_translationHistoryBottom", 1)[1].split("\n\t@", 1)[0]
    assert "_syncTranslationReviewPosition(True, atEnd=True)" in bottom_script

    line_navigation = addon_source.split("def _moveTranslationHistoryLine", 1)[1].split("\n\tdef ", 1)[0]
    assert "if updated == text:" in line_navigation
    assert "已到最新一筆翻譯紀錄。" in line_navigation

    sync_method = addon_source.split("def _syncTranslationReviewPosition", 1)[1].split("\n\tdef ", 1)[0]
    assert "_translationReviewInfoAtOffset(obj, targetLine[0])" in sync_method
    assert "info.move(textInfos.UNIT_CHARACTER, targetLine[0])" not in sync_method

    offset_helper = addon_source.split("def _translationReviewInfoAtOffset", 1)[1].split("\ndef ", 1)[0]
    assert "makeTextInfo(textInfos.POSITION_FIRST)" in offset_helper
    assert "info._startOffset = target" in offset_helper
    assert "info._endOffset = target" in offset_helper
    assert ".move(" not in offset_helper

    overlay_method = addon_source.split("def chooseNVDAObjectOverlayClasses", 1)[1].split("\n\t@", 1)[0]
    for attribute in ("windowClassName", "windowControlID", "IAccessibleRole"):
        assert f'getattr(obj, "{attribute}", None)' in overlay_method, overlay_method

    print("NVDA_CHINESE_DISPLAY_OK safe_dialogue_pairing=yes structured_translation_preserved=yes")


if __name__ == "__main__":
    main()
