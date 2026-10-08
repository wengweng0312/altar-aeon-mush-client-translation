#!/usr/bin/env python3
"""Build a privacy-safe catalog of existing Mush-Z trigger structures.

The catalog stores trigger definitions and aggregate match counts only.  It
never stores the source text read from the translation trace.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import html
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


TRIGGER_RE = re.compile(r"<trigger\b(?P<attrs>[^>]*)>(?P<body>.*?)</trigger\s*>", re.I | re.S)
ATTR_RE = re.compile(r"([:\w-]+)\s*=\s*(['\"])(.*?)\2", re.S)
SEND_RE = re.compile(r"<send\b[^>]*>(.*?)</send\s*>", re.I | re.S)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
FIELD_RE = re.compile(r"\(\?P<([A-Za-z_]\w*)>")

TRANSLATION_TEMPLATES = (
    (100, "navigation", r"Alas, you cannot go that way\.", "可惜，你不能往那個方向走。", "exact mapper message"),
    (100, "navigation", r"The door is locked\.", "門鎖著。", "exact mapper message"),
    (100, "navigation", r"There is no exit in that direction\.", "那個方向沒有出口。", "exact mapper message"),
    (100, "navigation", r"You are regaining balance and are unable to move\.", "你正在恢復平衡，無法移動。", "exact mapper message"),
    (100, "navigation", r"You must be standing first\.", "你必須先站起來。", "exact mapper message"),
    (100, "navigation", r"You fumble about drunkenly\.", "你醉醺醺地蹣跚摸索。", "exact mapper message"),
    (100, "navigation", r"You are asleep and can do nothing\. WAKE will attempt to wake you\.", "你正在睡覺，什麼也做不了。輸入 WAKE 將嘗試醒來。", "exact mapper message"),
    (100, "navigation", r"You'll have to swim to make it through the water in that direction\.", "你必須游泳才能穿過那個方向的水域。", "exact mapper message"),
    (100, "navigation", r"As you stroll in, you feel your feet slipping on something slimy\.", "你走進去時，感覺腳踩在黏滑的東西上而開始打滑。", "exact mapper message"),
    (100, "navigation", r"You are surrounded by a pocket of air and so must move normally through water\.", "你被一團空氣包圍，因此必須以一般方式穿過水域。", "exact mapper message"),
    (100, "navigation", r"You need to use a boat, fly, or swim underwater to go there\.", "你需要乘船、飛行或在水下游泳才能前往那裡。", "exact mapper message"),
    (100, "navigation", r"Now now, don't be so hasty!", "別急，別這麼匆忙！", "exact mapper message"),
    (100, "item", r"Compared to your current equipment:", "與你目前的裝備相比：", "exact SID header"),
    (100, "item", r"Compared to your current weapon:", "與你目前的武器相比：", "exact SID header"),
    (100, "item", r"You are using:", "你正在使用：", "exact equipment header"),
    (100, "item", r"Item is affected by:", "物品受到以下效果影響：", "exact SID header"),
    (100, "item", r"Item affects you as:", "物品對你產生以下影響：", "exact SID header"),
    (100, "item", r"Item has other effects:", "物品還有其他效果：", "exact SID header"),
    (100, "item", r"Item is unwieldable\.", "此物品無法裝備使用。", "exact SID footer"),
    (100, "item", r"Weapon is unwieldable\.", "此武器無法揮舞使用。", "exact SID footer"),
    (100, "item", r"This weapon can make ranged attacks using arrows\.", "此武器可以使用箭矢進行遠程攻擊。", "exact SID footer"),
    (100, "item", r"This weapon has a well-defined blade that can rip and tear\.", "此武器具有輪廓分明、能撕裂目標的刀刃。", "exact SID footer"),
    (100, "item", r"This item is bound to your account\.", "此物品已綁定至你的帳號。", "exact binding state"),
    (100, "item", r"This item is bound to you\.", "此物品已綁定至你。", "exact binding state"),
    (100, "status", r"Alter Aeon Character List", "Alter Aeon 角色列表", "exact account-list header"),
    (100, "status", r"You haven't had a recent victory worth shouting about\.", "你最近沒有值得大聲宣揚的勝利。", "exact status message"),
    (100, "status", r"You slowly float to the ground\.", "你緩緩飄落到地面。", "exact status message"),
    (90, "status", r"You receive (?P<value>[^\r\n]+?) experience\.", "你獲得 {value} 點經驗值。", "preserve experience value"),
    (90, "status", r"You receive (?P<value>[^\r\n]+?) experience points\.", "你獲得 {value} 點經驗值。", "preserve experience value"),
    (90, "status", r"You have (?P<value>-?\d+) experience\.", "你有 {value} 點經驗值。", "preserve experience value"),
    (90, "status", r"You have (?P<value>[^\r\n]+?) experience points\.", "你有 {value} 點經驗值。", "preserve experience value"),
    (90, "status", r"You have lost (?P<value>-?\d+) experience\.", "你已損失 {value} 點經驗值。", "preserve experience value"),
    (90, "status", r"You have spent (?P<value>-?\d+) experience\.", "你已花費 {value} 點經驗值。", "preserve experience value"),
    (90, "status", r"You have lost (?P<value>-?\d+) experience points so far due to deaths\.", "截至目前，你因死亡損失了 {value} 點經驗值。", "preserve experience value"),
    (90, "status", r"You have spent \+(?P<value>\d+) experience points so far\.", "截至目前，你已花費 +{value} 點經驗值。", "preserve experience value"),
    (90, "status", r"You need (?P<cost>\w+) experience to train a practice, and you have (?P<value>\w+)\.", "訓練一點練習點數需要 {cost} 點經驗值，而你有 {value} 點。", "preserve training values"),
    (90, "status", r"You can train to get a practice, at a cost of (?P<cost>\d+) experience each\.", "你可以訓練取得練習點數，每點需要 {cost} 點經驗值。", "preserve training cost"),
    (90, "item", r"Weapon speed: (?P<value>[^\r\n]+)", "武器速度：{value}", "preserve weapon speed value"),
    (90, "item", r"Item is level (?P<value>\d+) grenade of type:", "物品是等級 {value} 的手榴彈，類型為：", "preserve grenade level"),
    (90, "item", r"Has (?P<used>\d+) of (?P<capacity>\d+) pounds\.", "容量：已使用 {used}／{capacity} 磅。", "preserve capacity values"),
    (90, "item", r"Estimated cost:\s+(?P<cost>\d+)\s*", "估計價格：{cost}", "preserve estimated cost"),
    (90, "item", r"Affects:\s+(?P<affect>[A-Z_]+) by (?P<value>-?[0-9]+(?:\.0|\.5)?)%?", "影響：{affect}，數值 {value}", "preserve affect code and value"),
    (90, "item", r"Affects:\s+(?P<affect>[A-Z_]+) by minus (?P<value>\d+(?:\.0|\.5)?)%?", "影響：{affect}，減少 {value}", "preserve affect code and value"),
    (90, "item", r"Wear locations are:\s+(?P<wear>[2A-Z_ ]+)", "可穿戴部位：{wear}", "translate finite wear-location codes"),
    (90, "item", r"A (?P<bottle>sun|star|moon)catcher bottle is (?P<fill_level>empty)\.", "{bottle}目前{fill_level}。", "translate finite bottle state"),
    (90, "item", r"It is (?P<fill_level>empty|quarter full|half full|three quarters full|full)\.\s+\((?P<used>\d+) pounds? out of (?P<capacity>\d+)\)", "目前{fill_level}（{used}／{capacity} 磅）。", "translate finite fill state and preserve capacity"),
    (90, "item", r"(?:Item|Brew) has level (?P<spell_level>[0-9]+) spells of:", "物品或藥劑含有以下等級 {spell_level} 的法術：", "preserve spell level"),
    (90, "status", r"You don't learn much from this battle, but still receive (?P<value>[^\r\n]+?) experience\.", "你沒有從這場戰鬥中學到多少，但仍獲得 {value} 點經驗值。", "preserve experience value"),
    (90, "status", r"You learn very little from this battle\.\s+You receive (?P<value>[^\r\n]+?) experience\.", "你從這場戰鬥中學到的很少。你獲得 {value} 點經驗值。", "preserve experience value"),
    (100, "quest", r"General Quest Info:", "任務概述：", "exact quest label"),
    (100, "quest", r"Current goal long description:", "目前目標詳細說明：", "exact quest label"),
    (100, "quest", r"You have discovered or been given the following quests:", "你已發現或接到以下任務：", "exact quest-list header"),
    (100, "quest", r"You can see more information with the 'quest info' command\.", "你可以使用 'quest info' 指令查看更多資訊。", "exact quest help"),
    (100, "quest", r"Complete a daily job\.", "完成一項每日工作。", "observed finite daily task"),
    (100, "quest", r"Gather a mushroom\.", "採集一朵蘑菇。", "observed finite daily task"),
    (100, "quest", r"Blind an opponent by throwing dirt at them\.", "向對手投擲泥土，使其失明。", "observed finite daily task"),
    (100, "quest", r"Rest a while by a fire\.", "在火堆旁休息一會兒。", "observed finite daily task"),
    (100, "quest", r"Read a book from the Great Library\.", "閱讀一本大圖書館的書。", "observed finite daily task"),
    (100, "quest", r"Completed a full attack combo\.", "完成一套完整的連擊。", "observed finite daily task"),
    (100, "quest", r"\(Final task complete, the reward will be given when you are no longer in combat\.\)", "（最後一項任務已完成；脫離戰鬥後將發放獎勵。）", "exact daily-task status"),
    (95, "quest", r"(?P<sign>[+-])(?P<value>\d[\d,]*(?:\.\d+)?[kKmMbB]?) xp!", "{sign}{value} 經驗值！", "preserve compact XP reward"),
    (95, "quest", r"You are too high level, but still receive (?P<value>[^\r\n]+?) experience\.", "你的等級太高，但仍獲得 {value} 點經驗值。", "preserve experience value"),
    (95, "quest", r"You receive (?P<value>[^\r\n]+?) experience!", "你獲得 {value} 點經驗值！", "preserve experience value"),
    (95, "quest", r"Complete the (?P<count>\d+) tasks below to gain a reward\.", "完成以下 {count} 項任務即可獲得獎勵。", "preserve daily-task count"),
    (95, "quest", r"You have completed (?P<count>\d+) tasks and have earned your reward!", "你已完成 {count} 項任務並獲得獎勵！", "preserve completed-task count"),
    (95, "quest", r"You receive (?P<value>\d[\d,]*) gambling gold!", "你獲得 {value} 枚賭博金幣！", "preserve gambling reward"),
    (100, "common", r"Your shadow double steps in to take your place in combat\.", "你的影子分身上前，在戰鬥中代替你。", "common combat system line"),
    (100, "common", r"You stealthily move into position\.\.\.", "你悄悄移動到適合的位置……", "common stealth line"),
    (100, "common", r"You slip expertly into your hiding spot\.", "你熟練地躲進藏身處。", "common stealth line"),
    (100, "common", r"You slip from the shadows\.", "你從陰影中現身。", "common stealth line"),
    (100, "common", r"You cry victory over your fallen enemy!", "你對倒下的敵人高呼勝利！", "common victory line"),
    (100, "common", r"You wait for an attack of opportunity\.\.\.", "你等待可乘之機……", "common combat stance line"),
    (100, "common", r"You give up waiting, and shift out of your riposte stance\.", "你放棄等待，退出反擊架勢。", "common combat stance line"),
    (100, "common", r"You follow through after your feint!", "你在佯攻後順勢追擊！", "common combat line"),
    (100, "common", r"You have some small wounds and bruises\.", "你有一些小傷口和瘀傷。", "common condition line"),
    (100, "common", r"You have quite a few wounds\.", "你有不少傷口。", "common condition line"),
    (100, "common", r"You have a few scratches\.", "你有幾處擦傷。", "common condition line"),
    (100, "common", r"You are surrounded by a white aura\.", "一道白色光環環繞著你。", "common spell-state line"),
    (100, "common", r"The white aura around your body fades\.", "環繞你身體的白色光環消退了。", "common spell-state line"),
    (100, "common", r"You feel a slight tingle and you feel somehow abandoned\.", "你感到一陣輕微刺麻，彷彿被遺棄了。", "common spell-state line"),
    (100, "common", r"Dark figures step from the shadows and solidify into exact replicas of you\.", "黑暗身影從陰影中走出，凝聚成與你一模一樣的分身。", "common shadow line"),
    (100, "common", r"A dark figure steps from the shadows and solidifies into an exact replica of you\.", "一個黑暗身影從陰影中走出，凝聚成與你一模一樣的分身。", "common shadow line"),
    (100, "common", r"You start swinging and spinning the blade, 'Mischief'\.\.\.", "你開始揮動並旋轉刀刃「Mischief」……", "preserve weapon proper name"),
    (100, "common", r"You feel less tired\.", "你感覺沒那麼疲倦了。", "common status line"),
    (100, "common", r"Tip!", "提示！", "common UI line"),
    (100, "common", r"You do not see that here\.", "你在這裡看不到那個東西。", "common command response"),
    (100, "common", r"You do not see that character here\.", "你在這裡看不到那個角色。", "common command response"),
    (100, "common", r"Your search comes up empty\.", "你的搜尋一無所獲。", "common search response"),
    (100, "common", r"You already have shadow decoys present\.", "你已經有影子誘餌存在。", "common shadow response"),
    (100, "common", r"You use your faith in Shift as a shield to protect you\.", "你以對 Shift 的信仰化為盾牌保護自己。", "preserve deity proper name"),
    (100, "common", r"You are using the latest version of Mush-Z\.", "你正在使用最新版的 Mush-Z。", "common client status"),
    (100, "common", r"Saving your character\.\.\.", "正在儲存你的角色……", "common save status"),
    (100, "status", r"You are full\.", "你完全恢復了。", "exact fully-restored status"),
    (100, "common", r"Stealth mode off\.", "隱密模式已關閉。", "common stealth status"),
    (100, "common", r"Cripple who\?", "要對誰施展 cripple？", "preserve command name"),
    (100, "common", r"You must be in melee combat to feign attacks\.", "你必須處於近戰中才能佯攻。", "common combat response"),
    (95, "common", r"Your next cheapest level is a tie for (?P<value>\d[\d,]*)", "你下一個最便宜的等級有多個並列，費用為 {value}。", "preserve level cost"),
)

FIELD_GLOSSARY = {
    "affect": {
        "ATTACK_SPEED": "攻擊速度", "CLER_CAST_LEVEL": "牧師施法等級",
        "THIEF_SKILL_LEVEL": "盜賊技能等級", "MAGE_CAST_LEVEL": "法師施法等級",
        "NECR_CAST_LEVEL": "死靈法師施法等級", "WARR_SKILL_LEVEL": "戰士技能等級",
        "DRUID_CAST_LEVEL": "德魯伊施法等級", "SAVING_FIRE": "火焰豁免",
        "SAVING_COLD": "寒冷豁免", "SAVING_ZAP": "電擊豁免",
        "SAVING_SPELL": "法術豁免", "SAVING_POISON": "毒素豁免",
        "SAVING_BREATH": "吐息豁免", "DAMROLL": "傷害加值",
        "HITROLL": "命中加值", "MOV_REGEN": "體力恢復",
        "MOVE_REGEN": "體力恢復", "HP_REGEN": "血量恢復",
        "MANA_REGEN": "法力恢復", "HP": "血量",
        "ALIGNMENT": "陣營值", "SPELL_RES": "法術抗性",
        "ABSORB_MAGIC": "魔法吸收", "ABSORB_FIRE": "火焰吸收",
        "ABSORB_ICE": "寒冷吸收", "ABSORB_ZAP": "電擊吸收",
        "CAST_ABILITY": "施法能力", "HIT_POINTS": "血量",
        "MOVE": "體力", "MV": "體力", "MOVEMENT": "體力", "MANA": "法力", "WIS": "智慧",
        "INT": "智力", "CON": "體質", "CHR": "魅力", "STR": "力量",
        "DEX": "敏捷", "SHIELD_BLOCK": "盾牌格擋", "PARRY": "招架",
        "DODGE": "閃避", "SNEAK": "潛行", "HIDE": "隱藏",
        "AGE": "年齡", "AGING": "老化", "SIZE": "體型",
        "LUCK": "幸運", "ARMOR": "護甲值",
        "WARRIOR_SKILL_LEVEL": "戰士技能等級",
        "CLERIC_CAST_LEVEL": "牧師施法等級",
    },
    "bottle": {"SUN": "日光瓶", "STAR": "星光瓶", "MOON": "月光瓶"},
    "fill_level": {
        "EMPTY": "空的", "CONTAINS A SMALL AMOUNT": "含有少量內容物",
        "QUARTER FULL": "四分之一滿", "HALF FULL": "半滿",
        "THREE QUARTERS FULL": "四分之三滿", "FULL": "已滿",
    },
    "quality": {
        "WELL MADE": "製作良好", "WELL CRAFTED": "工藝精良",
        "EXPERTLY CRAFTED": "專家打造", "MASTERCRAFT": "大師工藝",
        "MASTERCRAFT LEVEL 2": "大師工藝等級 2",
        "MASTERCRAFT LEVEL 3": "大師工藝等級 3", "EXCEPTIONAL": "卓越",
    },
    "item_type": {
        "ARMOR": "護甲", "WEAPON": "武器", "CLOTHING": "衣物",
        "TREASURE": "寶物", "MAGIC": "魔法物品", "SPELLCOMP": "法術材料",
        "POTION": "藥水", "OTHER": "其他", "FOCUS": "法器",
        "CONTAINER": "容器", "SPELLBOOK": "法術書",
    },
    "speed": {
        "SLOWEST": "最慢", "VERY SLOW": "非常慢", "SLOW": "慢",
        "AVERAGE": "普通", "FAST": "快", "VERY FAST": "非常快",
    },
    "composition": {
        "BASE METAL": "基礎金屬", "METAL": "金屬", "IRON": "鐵",
        "SILVER": "銀", "GOLD": "黃金", "COPPER": "銅", "ZINC": "鋅",
        "MITHRIL": "秘銀", "METAL ALLOY": "金屬合金", "STEEL": "鋼",
        "TEXTILE": "紡織物", "FABRIC": "布料", "SILK": "絲綢", "WOOL": "羊毛",
        "TIMBER": "木材", "WOOD": "木頭", "FLESH": "血肉", "SKIN": "皮膚",
        "SKELETON": "骨骼", "BONE": "骨頭", "SHELL": "甲殼",
        "MINERAL": "礦物", "CRYSTAL": "水晶", "ROCK": "岩石",
        "DRY": "乾燥", "PAPER": "紙", "WET": "潮濕", "ORGANIC": "有機物",
        "NON-SOLID": "非固體", "MAGIC": "魔法", "CORPSE": "屍體",
        "VITREOUS": "玻璃質", "BLACK OBSIDIAN": "黑曜石",
        "VEGETATION": "植物", "BARK": "樹皮", "BURLAP": "粗麻布",
        "MARBLE": "大理石", "VOID": "虛空物質", "VOID METAL": "虛空金屬",
        "QUARTZITE": "石英岩", "ARJALE": "Arjale", "HEMATIUM": "Hematium",
        "RUBY": "紅寶石", "BLACKWOOD": "黑木", "BLUE GOLD": "藍金", "BRASS": "黃銅",
    },
    "flag": {
        "ARTIFACT": "神器", "GLOW": "發光", "LIGHT": "照明",
        "HUM": "嗡鳴", "QUEST_ITEM": "任務物品", "RARE": "稀有",
        "MAGE": "法師", "CLERIC": "牧師", "THIEF": "盜賊",
        "WARRIOR": "戰士", "NECR": "死靈法師", "DRUID": "德魯伊",
        "BOUND": "綁定", "ACCOUNT_BOUND": "帳號綁定", "FLOATING": "漂浮",
        "ANTI_GOOD": "排斥善良", "ANTI_EVIL": "排斥邪惡",
        "ANTI_NEUTRAL": "排斥中立", "EVIL": "邪惡", "RELIC": "遺物",
        "KEEP": "保留", "JUNK": "廢棄品", "FRAGILE": "易碎",
        "NO_BACKSTAB": "不可背刺", "POISON": "帶毒",
    },
    "wear": {
        "HELD": "手持", "WEAPON": "武器", "HEAD": "頭部", "NECK": "頸部",
        "ARMS": "手臂", "WRIST": "手腕", "HANDS": "雙手", "FINGERS": "手指",
        "BODY": "身體", "ABOUT_BODY": "披掛", "WAIST": "腰部", "LEGS": "腿部",
        "FEET": "腳部", "SHIELD": "盾牌", "2_WIELD": "雙持",
        "WRISTS": "手腕", "ON_BODY": "身上",
    },
}

SKIP_PARTS = {
    "release", "lmt_runtime", "python_runtime", "__pycache__", "logs",
    "translation_bridge",
}
SKIP_NAME_FRAGMENTS = ("backup", ".bak", "copy of ", "old_")


def truthy(value: str, default: bool = False) -> bool:
    if value == "":
        return default
    return value.strip().lower() in {"y", "yes", "true", "1"}


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    return re.sub(r"\s+", " ", value).strip()


def classify(path: Path, attrs: dict[str, str], send: str, fields: list[str]) -> tuple[str, str, int, str, str]:
    pattern = attrs.get("match", "")
    blob = " ".join((path.name, attrs.get("name", ""), attrs.get("group", ""),
                     attrs.get("script", ""), pattern, send)).lower()
    internal = any(x in blob for x in ("kxwt_", "mushz_error", "pluginbroadcast", "enabletrigger", "enablegroup"))
    sound = any(x in blob for x in ("playsound", "sound(", ".wav", ".ogg", ".mp3", "sound/", "sound\\"))
    navigation = any(x in blob for x in ("waypoint", "mapper", "direction", "exits", "roomnum", "room_id"))
    item = any(x in blob for x in ("sid_item", "inventory", "carrying", "weapon", "armor", "weight", "condition"))
    status = any(x in blob for x in ("health", "mana", "movement", "level", "experience", "affect", "stat"))
    combat = any(x in blob for x in ("combat", "damage", "critical", "kill", "death", "attack"))
    channel = any(x in blob for x in ("channel", "chat", "tell", "clan", "gossip"))

    if internal:
        category, purpose = "control", "client control/internal protocol"
    elif item:
        category, purpose = "item", "item or inventory structure"
    elif navigation:
        category, purpose = "navigation", "room, exit, or waypoint structure"
    elif status:
        category, purpose = "status", "character state or numeric status"
    elif combat:
        category, purpose = "combat", "combat event"
    elif channel:
        category, purpose = "channel", "player communication"
    elif sound:
        category, purpose = "event", "event currently used by audio feedback"
    elif fields:
        category, purpose = "data", "captured structured fields"
    else:
        category, purpose = "other", "unclassified trigger"

    enabled = truthy(attrs.get("enabled", "y"), True)
    output_hidden = truthy(attrs.get("omit_from_output", "n"))
    normalized = re.sub(r"\s+", "", pattern)
    broad = (
        normalized in {"*", ".*", "^.*$", "(*)"}
        or ("(.*)" in normalized and len(normalized) < 24)
        or normalized.startswith("^(?!") and normalized.endswith("(.*)$")
    )
    candidate = int(enabled and not internal and not broad and bool(pattern)
                    and (bool(fields) or sound or navigation or item or status or combat))
    if internal:
        risk = "high"
    elif output_hidden or channel:
        risk = "medium"
    elif fields:
        risk = "low"
    else:
        risk = "review"
    notes = []
    if sound:
        notes.append("sound_event")
    if output_hidden:
        notes.append("hidden_output")
    if fields:
        notes.append("named_fields")
    if broad:
        notes.append("broad_catchall")
    return category, purpose, candidate, risk, ",".join(notes)


def wildcard_to_regex(pattern: str) -> str:
    # MUSHclient non-regexp triggers use * and ? wildcards.  Preserve named
    # information only for regexp triggers; this is solely for aggregate counts.
    translated = fnmatch.translate(pattern)
    return translated


def compile_pattern(pattern: str, is_regexp: bool) -> tuple[re.Pattern[str] | None, str]:
    if not pattern:
        return None, "empty"
    try:
        return re.compile(pattern if is_regexp else wildcard_to_regex(pattern), re.I), "ok"
    except re.error as exc:
        return None, f"python_incompatible: {exc}"


def discover_sources(root: Path) -> list[Path]:
    files = []
    candidates = list(root.rglob("*.xml")) + list(root.rglob("*.lua"))
    for path in candidates:
        rel_parts = {p.lower() for p in path.relative_to(root).parts[:-1]}
        lower_name = path.name.lower()
        if rel_parts & SKIP_PARTS:
            continue
        if any(fragment in lower_name for fragment in SKIP_NAME_FRAGMENTS):
            continue
        # Several core Mush-Z trigger collections are Lua files containing an
        # XML document string (notably sound_xml.lua).  Catalog only Lua files
        # that actually contain trigger definitions; ordinary Lua code is not
        # useful here.
        if path.suffix.lower() == ".lua":
            try:
                if "<trigger" not in path.read_text(encoding="utf-8-sig", errors="replace").lower():
                    continue
            except OSError:
                continue
        files.append(path)
    return sorted(files, key=lambda p: str(p).lower())


def parse_triggers(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    active = COMMENT_RE.sub("", raw)
    rows = []
    for ordinal, match in enumerate(TRIGGER_RE.finditer(active), 1):
        attrs = {key.lower(): html.unescape(value) for key, _, value in ATTR_RE.findall(match.group("attrs"))}
        body = match.group("body")
        sends = [clean_text(x) for x in SEND_RE.findall(body)]
        send = "\n".join(x for x in sends if x)
        pattern = attrs.get("match", "")
        fields = list(dict.fromkeys(FIELD_RE.findall(pattern)))
        category, purpose, candidate, risk, notes = classify(path, attrs, send, fields)
        is_regexp = truthy(attrs.get("regexp", "n"))
        compiled, compile_status = compile_pattern(pattern, is_regexp)
        rows.append({
            "ordinal": ordinal, "attrs": attrs, "send": send, "pattern": pattern,
            "fields": fields, "category": category, "purpose": purpose,
            "candidate": candidate, "risk": risk, "notes": notes,
            "compiled": compiled, "compile_status": compile_status,
        })
    return rows


def load_trace_counts(traces: list[Path] | None) -> tuple[Counter[str], int]:
    counts: Counter[str] = Counter()
    records = 0
    for trace in traces or []:
        if not trace.exists():
            continue
        with trace.open("r", encoding="utf-8-sig", errors="replace") as handle:
            for line in handle:
                try:
                    source = json.loads(line).get("source", "")
                except (json.JSONDecodeError, AttributeError):
                    continue
                if not isinstance(source, str):
                    continue
                records += 1
                for source_line in source.splitlines():
                    counts[source_line] += 1
    return counts, records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mush-root", type=Path, required=True)
    parser.add_argument("--trace", type=Path, action="append")
    parser.add_argument("--output", type=Path, default=Path("mush_structure_catalog.sqlite3"))
    parser.add_argument("--report", type=Path, default=Path("mush_structure_catalog_report.txt"))
    args = parser.parse_args()

    root = args.mush_root.resolve()
    source_files = discover_sources(root)
    line_counts, trace_records = load_trace_counts(args.trace)
    parsed = [(path, parse_triggers(path)) for path in source_files]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()
    db = sqlite3.connect(args.output)
    db.executescript("""
        PRAGMA journal_mode=DELETE;
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE sources (
          id INTEGER PRIMARY KEY, relative_path TEXT UNIQUE NOT NULL,
          sha256 TEXT NOT NULL, trigger_count INTEGER NOT NULL, scope TEXT NOT NULL
        );
        CREATE TABLE triggers (
          id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id),
          ordinal INTEGER NOT NULL, name TEXT, group_name TEXT, pattern TEXT NOT NULL,
          is_regexp INTEGER NOT NULL, enabled INTEGER NOT NULL, script TEXT, send_to TEXT,
          sequence TEXT, omit_from_output INTEGER NOT NULL, omit_from_log INTEGER NOT NULL,
          keep_evaluating INTEGER NOT NULL, send_body TEXT, category TEXT NOT NULL,
          purpose TEXT NOT NULL, deterministic_candidate INTEGER NOT NULL, risk TEXT NOT NULL,
          notes TEXT, compile_status TEXT NOT NULL, observed_count INTEGER NOT NULL DEFAULT 0,
          UNIQUE(source_id, ordinal)
        );
        CREATE TABLE trigger_fields (
          trigger_id INTEGER NOT NULL REFERENCES triggers(id), ordinal INTEGER NOT NULL,
          field_name TEXT NOT NULL, PRIMARY KEY(trigger_id, ordinal)
        );
        CREATE TABLE translation_templates (
          id INTEGER PRIMARY KEY, priority INTEGER NOT NULL, category TEXT NOT NULL,
          source_regex TEXT UNIQUE NOT NULL, output_template TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1, notes TEXT
        );
        CREATE TABLE field_glossary (
          field_name TEXT NOT NULL, source_value TEXT NOT NULL,
          translated_value TEXT NOT NULL,
          PRIMARY KEY(field_name, source_value)
        );
        CREATE INDEX idx_triggers_category ON triggers(category);
        CREATE INDEX idx_triggers_candidate ON triggers(deterministic_candidate, observed_count DESC);
        CREATE INDEX idx_fields_name ON trigger_fields(field_name);
    """)
    now = datetime.now(timezone.utc).isoformat()
    metadata = {
        "schema_version": "1", "generated_utc": now,
        "source_root_label": "Mush-Z", "privacy": "definitions_and_aggregate_counts_only",
        "trace_records_scanned": str(trace_records),
        "source_files_scanned": str(len(source_files)),
        "xml_files_scanned": str(sum(path.suffix.lower() == ".xml" for path in source_files)),
        "lua_trigger_files_scanned": str(sum(path.suffix.lower() == ".lua" for path in source_files)),
    }
    db.executemany("INSERT INTO metadata(key,value) VALUES (?,?)", metadata.items())
    db.executemany(
        "INSERT INTO translation_templates(priority,category,source_regex,output_template,enabled,notes) VALUES (?,?,?,?,1,?)",
        TRANSLATION_TEMPLATES,
    )
    db.executemany(
        "INSERT INTO field_glossary(field_name,source_value,translated_value) VALUES (?,?,?)",
        ((field, source, translated) for field, values in FIELD_GLOSSARY.items()
         for source, translated in values.items()),
    )

    total = compatible = observed_triggers = 0
    category_counts: Counter[str] = Counter()
    candidates: list[tuple[int, str, str, str, str]] = []
    for path, triggers in parsed:
        rel = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        scope = rel.split("/", 1)[0] if "/" in rel else "root"
        source_id = db.execute(
            "INSERT INTO sources(relative_path,sha256,trigger_count,scope) VALUES (?,?,?,?)",
            (rel, digest, len(triggers), scope),
        ).lastrowid
        for row in triggers:
            attrs = row["attrs"]
            observed = 0
            if row["compiled"] is not None:
                compatible += 1
                for source_line, count in line_counts.items():
                    if row["compiled"].search(source_line):
                        observed += count
            trigger_id = db.execute("""
                INSERT INTO triggers(source_id,ordinal,name,group_name,pattern,is_regexp,enabled,
                  script,send_to,sequence,omit_from_output,omit_from_log,keep_evaluating,send_body,
                  category,purpose,deterministic_candidate,risk,notes,compile_status,observed_count)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                source_id, row["ordinal"], attrs.get("name", ""), attrs.get("group", ""), row["pattern"],
                int(truthy(attrs.get("regexp", "n"))), int(truthy(attrs.get("enabled", "y"), True)),
                attrs.get("script", ""), attrs.get("send_to", ""), attrs.get("sequence", ""),
                int(truthy(attrs.get("omit_from_output", "n"))), int(truthy(attrs.get("omit_from_log", "n"))),
                int(truthy(attrs.get("keep_evaluating", "n"))), row["send"], row["category"],
                row["purpose"], row["candidate"], row["risk"], row["notes"], row["compile_status"], observed,
            )).lastrowid
            db.executemany("INSERT INTO trigger_fields(trigger_id,ordinal,field_name) VALUES (?,?,?)",
                           ((trigger_id, i, field) for i, field in enumerate(row["fields"], 1)))
            total += 1
            category_counts[row["category"]] += 1
            observed_triggers += int(observed > 0)
            if row["candidate"]:
                candidates.append((observed, rel, attrs.get("name", ""), row["category"], row["pattern"]))
    db.commit()
    db.close()

    candidates.sort(key=lambda x: (-x[0], x[1].lower(), x[2].lower()))
    report_lines = [
        "Mush-Z structure catalog report", f"Generated UTC: {now}",
        f"Trigger source files scanned: {len(source_files)}",
        f"XML files scanned: {metadata['xml_files_scanned']}",
        f"Lua trigger files scanned: {metadata['lua_trigger_files_scanned']}",
        f"Triggers cataloged: {total}",
        f"Python-compatible patterns: {compatible}", f"Trace records scanned: {trace_records}",
        f"Triggers observed in trace: {observed_triggers}", "",
        "Categories:",
    ]
    report_lines.extend(f"  {name}: {count}" for name, count in category_counts.most_common())
    report_lines.extend(["", "Top deterministic candidates by aggregate observed count:"])
    for count, rel, name, category, pattern in candidates[:80]:
        short_pattern = pattern.replace("\n", "\\n")[:180]
        report_lines.append(f"  {count:7d}  [{category}] {rel} :: {name or '(unnamed)'} :: {short_pattern}")
    report_lines.extend(["", "Privacy: no matched player text is stored in the database or this report."])
    args.report.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"catalog={args.output} triggers={total} files={len(source_files)} trace_records={trace_records}")
    print(f"report={args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
