"""Offline regressions for reviewed visible trigger/filter event shells."""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "translation_bridge" / "translation_worker.py"
FUNCTIONS = {
    "semantic_event_match",
    "translate_semantic_event_line",
    "is_semantic_event_block",
    "prefetch_semantic_event_fields",
    "translate_semantic_event_block",
    "deterministic_translate",
}


def load_functions() -> dict[str, object]:
    tree = ast.parse(WORKER.read_text(encoding="utf-8-sig"))
    body = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "SEMANTIC_EVENT_PATTERNS"
            for target in node.targets
        ):
            body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
            body.append(node)
    translations = {
        "a crescent-shaped shadow": "一道新月形陰影",
        "A small troll": "一隻小巨魔",
        "A shadow decoy": "一個暗影誘餌",
        "a shadow decoy": "一個暗影誘餌",
        "Hawana": "Hawana",
        "crystal coat": "水晶外衣",
        "Shift": "Shift",
        "the corpse of A small troll": "一隻小巨魔的屍體",
        "First Steps": "第一步",
        "an azure blue mask": "一個天藍色面具",
        "Tensor's floating disc": "Tensor 的浮空圓盤",
        "the mask of an assassin": "刺客面具",
        "the large set of oak doors": "那扇大型橡木門",
        "large set of oak doors": "那扇大型橡木門",
        "Silvermoon": "Silvermoon",
        "pound": "重擊",
        "a steel sword": "一把鋼劍",
        "an iron sword": "一把鐵劍",
        "Moondoggie": "Moondoggie",
        "a healing potion": "一瓶治療藥水",
    }
    namespace = {
        "re": re,
        "translate_cached_phrase": lambda value, _config: translations.get(value, value),
        "numeric_values": lambda value: re.findall(r"\d[\d,]*(?:\.\d+)?[kKmMbB]?", value),
        "numeric_items_preserved": lambda source, result: all(
            item in result for item in re.findall(r"\d[\d,]*(?:\.\d+)?[kKmMbB]?", source)
        ),
        "log": lambda *_args, **_kwargs: None,
        "prefetch_cached_phrases": lambda _values, _config: None,
    }
    exec(compile(ast.Module(body=body, type_ignores=[]), str(WORKER), "exec"), namespace)
    return namespace


def main() -> None:
    module = load_functions()
    translate = module["translate_semantic_event_line"]
    cases = {
        "You start swinging and spinning the blade, 'Mischief'...": "你開始揮動並旋轉刀刃「Mischief」……",
        "You flick the blade, 'Mischief' at A small troll, and score a quick hit!": "你將刀刃「Mischief」迅速揮向一隻小巨魔，成功擊中！",
        "You flick the blade, 'Mischief', but A small troll avoids your attack.": "你將刀刃「Mischief」迅速揮向一隻小巨魔，但對方避開了攻擊。",
        "A small troll makes a strange noise as you place the blade, 'Mischief' in his back.": "當你將刀刃「Mischief」刺入一隻小巨魔背部時，對方發出奇怪的聲音。",
        "Hawana puts an azure blue mask in Tensor's floating disc.": "Hawana將一個天藍色面具放入Tensor 的浮空圓盤。",
        "You are carrying the mask of an assassin.": "你攜帶著刺客面具。",
        "You open the large set of oak doors.": "你打開那扇大型橡木門。",
        "The large set of oak doors is closed.": "那扇大型橡木門關著。",
        "You receive 7 gold coins for your sacrifice of the corpse of A small troll.": "你奉獻一隻小巨魔的屍體，獲得 7 枚金幣。",
        "You have some small wounds and bruises.": "你有一些小傷口和瘀青。",
        "The physical reserve deep within you feels replenished.": "你體內深處的體力儲備已經恢復。",
        "You sense a hidden life form in the room.": "你感覺到房間裡有隱藏的生命。",
        "You pray to Shift for transportation...": "你向Shift祈求傳送……",
        "Silvermoon flies north.": "Silvermoon往北方飛走。",
        "A small troll's pound DISMEMBERS a shadow decoy!": "一隻小巨魔的重擊對一個暗影誘餌造成肢解!",
        "The white aura around Hawana fades.": "Hawana身旁的白色光環消退了。",
        "Hawana is surrounded by a white aura.": "Hawana被白色光環包圍。",
        "Moondoggie restored you to full health!": "Moondoggie使你完全恢復健康！",
        "You get 25 gold coins.": "你取得 25 枚金幣。",
        "You get 25 gold coins from A small troll.": "你從一隻小巨魔取得 25 枚金幣。",
        "You drop 25 gold coins.": "你丟下 25 枚金幣。",
        "Hawana gives you a healing potion.": "Hawana將一瓶治療藥水交給你。",
        "a steel sword looks better than an iron sword.": "一把鋼劍看起來比一把鐵劍好。",
        "Hawana starts following you.": "Hawana開始跟隨你。",
        "You start following Hawana.": "你開始跟隨Hawana。",
        "You add Hawana to your group.": "你將Hawana加入隊伍。",
        "Hawana has become a member of the group.": "Hawana加入了隊伍。",
        "Hawana vanishes into a flickering red glow.": "Hawana消失在閃爍的紅光中。",
        "a steel sword (unique)": "一把鋼劍（唯一）",
        "You get a crescent-shaped shadow.": "你取得一道新月形陰影。",
        "You drop a crescent-shaped shadow.": "你丟下一道新月形陰影。",
        "Hawana casts 'crystal coat'": "Hawana施放「水晶外衣」。",
        "Hawana is here.": "Hawana在這裡。",
        "Hawana is darkened.": "Hawana籠罩在黑暗中。",
        "You receive 230k experience.": "你獲得 230k 點經驗值。",
        "You gain favor in the eyes of Shift!": "你獲得Shift的青睞！",
        "You have completed the achievement: First Steps": "你完成了成就：第一步",
        "Shift appreciates your sacrifice of the corpse of A small troll.": "你將一隻小巨魔的屍體奉獻給Shift。",
        "A shadow decoy misses A small troll.": "一個暗影誘餌沒有擊中一隻小巨魔。",
        "A shadow decoy dodges A small troll's attack.": "一個暗影誘餌閃避了一隻小巨魔的攻擊。",
        "A small troll is mortally wounded, and will die soon if not aided.": "一隻小巨魔受到致命傷，若未獲救很快便會死亡。",
    }
    for source, expected in cases.items():
        actual = translate(source, {})
        assert actual == expected, (source, actual, expected)

    aggregate = "You get 2 items: a cup, a plate."
    assert module["semantic_event_match"](aggregate) is None
    block = "A shadow decoy misses A small troll.\nYou receive 230k experience."
    rendered = module["translate_semantic_event_block"](block, {})
    assert rendered.count("\n") == block.count("\n")
    assert "230k" in rendered
    worker_source = WORKER.read_text(encoding="utf-8-sig")
    assert "STRUCTURED_FIELD_CACHE_VERSION = 1" in worker_source
    assert 'missing[start:start + 32]' in worker_source
    assert 'prefetch_semantic_event_fields(lines, c)' in worker_source
    assert 'any(deterministic_translate(line.strip()) is not None' in worker_source
    deterministic = module["deterministic_translate"]
    health_conditions = {
        "excellent": "狀態極佳",
        "scratches": "輕微擦傷",
        "small wounds": "一些小傷口",
        "quite a few": "傷勢不少",
        "big nasty": "嚴重傷勢",
        "pretty hurt": "傷得很重",
        "awful": "傷勢危急",
    }
    for source, expected in health_conditions.items():
        assert deterministic(source) == expected
    assert deterministic("You receive an explorer point!") == "你獲得 1 點探索點數！"
    assert deterministic("Your ice shield fades and is gone.") == "你的冰盾消退並消失了。"
    print("SEMANTIC_EVENTS_OK cases=%d aggregate_safe=yes" % len(cases))


if __name__ == "__main__":
    main()
