# Mush-Z asynchronous translation worker - LMT-60 1.7B Q4 live integration
# Minimal first-run build: preserve inbox/outbox/cache protocol; replace MADLAD with persistent llama-server.
import base64, ctypes, hashlib, importlib.util, json, locale, os, platform, re, sqlite3, subprocess, sys, threading, time, urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent
_CLOUD_CLIENT_SPEC = importlib.util.spec_from_file_location(
    "mushz_cloud_translation_client", ROOT / "cloud_translation_client.py"
)
cloud_translation_client = importlib.util.module_from_spec(_CLOUD_CLIENT_SPEC)
_CLOUD_CLIENT_SPEC.loader.exec_module(cloud_translation_client)
INBOX, OUTBOX = ROOT/"inbox", ROOT/"outbox"
LOCK = ROOT/"worker.lock"
CONFIG = ROOT/"translation_config.json"
CLOUD_CONFIG = ROOT/"cloud_translation_config.txt"
LOG = ROOT/"translation_worker.log"
CACHE_DB = ROOT/"translation_cache.sqlite3"
SERVER_LOG = ROOT/"llama_server.log"
TRACE_LOG = ROOT/"lmt_translation_trace.log"
API_USAGE_FILE = ROOT/"cloud_api_local_usage.json"
LOG_ARCHIVE = ROOT/"log_archive"
TRACE_LOG_MAX_BYTES = 20 * 1024 * 1024
WORKER_LOG_MAX_BYTES = 5 * 1024 * 1024
SKILL_GLOSSARY_FILE = ROOT/"skill_glossary_zh_tw.json"
LIBRARY_GLOSSARY_FILE = ROOT/"library_glossary_zh_tw.json"
GAME_GLOSSARY_FILE = ROOT/"game_glossary_zh_tw.json"
PHRASE_GLOSSARY_FILE = ROOT/"phrase_glossary_zh_tw.json"
STRUCTURE_CATALOG_FILE = ROOT/"mush_structure_catalog.sqlite3"
BACKEND_CHOICE_FILE = ROOT/"backend_choice.json"
FORCE_BACKEND_BENCHMARK_FILE = ROOT/"benchmark_lmt_next_start.flag"
SESSION_FILE = Path(sys.argv[1]) if len(sys.argv) > 1 else None
SESSION_MAX_AGE = 4.0
CACHE_CONNECTION = None
CACHE_DISABLED = False
SERVER_PROCESS = None
SERVER_BACKEND = None
SERVER_THREADS = None
SERVER_READY = False
SERVER_STARTING = False
SERVER_START_ERROR = None
SERVER_START_OWNER = None
SERVER_START_THREAD = None
SERVER_START_EVENT = threading.Event()
SERVER_START_LOCK = threading.Lock()
SERVER_SHUTTING_DOWN = False
SERVER_ALLOW_AUTOTUNE = False
ACTIVE_CANDIDATE = None
CLOUD_FAILURE_COUNT = {1: 0, 2: 0, 3: 0}
CLOUD_DISABLED_UNTIL = {1: 0.0, 2: 0.0, 3: 0.0}
CLOUD_DISABLED_FOR_SESSION = set()
TRANSLATION_ENGINES_USED = set()
SKILL_GLOSSARY = None
LIBRARY_GLOSSARY = None
GAME_GLOSSARY = None
PHRASE_GLOSSARY = None
DETERMINISTIC_TEMPLATES = None
DETERMINISTIC_FIELD_GLOSSARY = None
PORT = 18082
CONTROL_CLEAR_RECENT_CACHE = "__MUSHZ_CONTROL_CLEAR_RECENT_CACHE__:"
CONTROL_TRANSLATE_OUTGOING_CHAT = "__MUSHZ_CONTROL_TRANSLATE_OUTGOING_CHAT__:"
CONTROL_CHECK_API = "__MUSHZ_CONTROL_CHECK_API__"
CPU_AUTOTUNE_VERSION = 1
STRUCTURED_FIELD_CACHE_VERSION = 2
CPU_AUTOTUNE_MIN_GAIN = 1.05
CLOUD_FAILURE_LIMIT = 3
CLOUD_COOLDOWN_SECONDS = 300

DEFAULT = {
    "provider":"lmt_q4",
    "source_language":"en",
    "target_language":"zh",
    "context_segments":3,
    "debug_logging":False,
    "request_timeout_seconds":25,
    "translation_cache_enabled":True,
    "translation_cache_max_entries":10000,
    "translation_cache_version":13
}

CLOUD_TRANSLATION_DEFAULT = {
    "service": 0,
    "api_keys": {1: "", 2: "", 3: ""},
    "azure_region": "global",
    "timeout_seconds": 1.5,
    "allow_private_messages": False,
}

PROMPT_PREFIX = "Translate the following English text into Traditional Chinese. Preserve proper names and do not add explanations.\nEnglish: "
ROBUST_PROMPT_PREFIX = ("Translate every line of the following English text into Traditional Chinese. "
                        "Preserve proper names, all digits, percentages, item order, and line order exactly. "
                        "Do not omit, summarize, repeat, or add explanations.\nEnglish: ")
PROMPT_SUFFIX = "\nTraditional Chinese:"
OFFICIAL_PROMPT_TEMPLATE = "Translate the following text from English into Chinese:\nEnglish: {text}\nChinese:"

STRUCTURED_EXACT_HEADERS = {
    "You are carrying:": "你正攜帶著：",
    "The following items are available for sale at this time:": "目前有以下物品可供出售：",
    "The following spell castings may be purchased for a small fee:": "支付少量費用即可購買以下法術施放服務：",
    "The following items are currently up for grabs:": "目前可免費取用以下物品：",
    "carried contains:": "隨身容器包含：",
    "on ground contains:": "地面容器包含：",
}
STRUCTURED_CONTAINS_MARKERS = {
    "carried contains:": "carried_container",
    "on ground contains:": "ground_container",
}

WEEKDAY_ZH = {
    "Mon": "星期一", "Tue": "星期二", "Wed": "星期三",
    "Thu": "星期四", "Fri": "星期五", "Sat": "星期六", "Sun": "星期日",
}
MONTH_ZH = {
    "Jan": "一月", "Feb": "二月", "Mar": "三月", "Apr": "四月",
    "May": "五月", "Jun": "六月", "Jul": "七月", "Aug": "八月",
    "Sep": "九月", "Oct": "十月", "Nov": "十一月", "Dec": "十二月",
}
INVENTORY_TIMESTAMP = re.compile(
    r"^New inventory last added on "
    r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun) "
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
    r"(\d{1,2}) (\d{1,2}:\d{2}:\d{2}) (\d{4})$"
)
DIRECTION_LINE = re.compile(r"^(\s*)Direction\s*->\s*([A-Za-z]+)(\s*)$", re.IGNORECASE)
DIRECTION_NAMES = {
    "N": "北", "S": "南", "E": "東", "W": "西", "U": "上", "D": "下",
    "NE": "東北", "NW": "西北", "SE": "東南", "SW": "西南",
}
NEARBY_MAP_SEARCH_HEADER = re.compile(
    r"^You consult your maps for nearby areas named '([^']*)':$", re.IGNORECASE
)
NEARBY_MAP_ROW = re.compile(
    r"^(\s*)Lvl\s+(\d+)\s+(.+?)\s+(?:is|are)\s+"
    r"(a very short distance|a short distance|a fair distance|far away),?\s+"
    r"to the (north|south|east|west|northeast|northwest|southeast|southwest)\.(\s*)$",
    re.IGNORECASE,
)
NEARBY_MAP_DIRECTIONS = {
    "north": "北", "south": "南", "east": "東", "west": "西",
    "northeast": "東北", "northwest": "西北",
    "southeast": "東南", "southwest": "西南",
}
NEARBY_MAP_DISTANCES = {
    "a very short distance": "距離非常近",
    "a short distance": "距離不遠",
    "a fair distance": "有一段距離",
    "far away": "距離很遠",
}
SCAN_HEADER = re.compile(r"^You scan the surrounding area\.\.\.$", re.IGNORECASE)
SCAN_ENTITY_ROW = re.compile(
    r"^(North|South|East|West|Northeast|Northwest|Southeast|Southwest|Up|Down)"
    r"\s+(\d+)\s+-\s+(.+?)\s*$",
    re.IGNORECASE,
)
SCAN_PAREN_ROW = re.compile(
    r"^\((north|south|east|west|northeast|northwest|southeast|southwest|up|down)\)\s+(.+?)\s*$",
    re.IGNORECASE,
)
SCAN_DIRECTIONS = {
    "north": "北", "south": "南", "east": "東", "west": "西",
    "northeast": "東北", "northwest": "西北",
    "southeast": "東南", "southwest": "西南", "up": "上", "down": "下",
}
SCAN_DOOR_MATERIALS = {
    "wooden": "木", "wood": "木", "stone": "石", "iron": "鐵",
    "steel": "鋼", "bronze": "青銅", "brass": "黃銅", "oak": "橡木",
}
SCAN_DOOR_STATES = {
    "closed": "緊閉", "open": "敞開", "locked": "上鎖",
}
BONUS_FIELD_ZH = {
    "movement": "體力", "hitpoints": "血量", "hit points": "血量",
    "mana": "法力", "morale": "士氣", "armor": "護甲",
    "warrior skill level": "戰士技能等級", "thief skill level": "盜賊技能等級",
    "mage cast level": "法師施法等級", "cleric cast level": "牧師施法等級",
    "druid cast level": "德魯伊施法等級", "necromancer cast level": "死靈法師施法等級",
}
LIBRARY_HEADER = re.compile(r"^\s*AABN\s*-\s*Book Title\s*$", re.IGNORECASE)
LIBRARY_ROW = re.compile(r"^(\s*)(\d+)(\s*-\s*)(.*?)(\s*)$")
QUEST_LIST_ROW = re.compile(r"^(\s*)Quest\s+(\d+)\s+-\s+(.*?)(\s+\[ACTIVE\])?(\s*)$", re.IGNORECASE)
QUEST_AVAILABLE_ROW = re.compile(r"^(\s*)\[\s*(\d+)\]\s*(.*?)(\s*)$", re.IGNORECASE)
JOB_LIST_ROW = re.compile(r"^(\s*)Job\s+(\d+)\s*:\s*(.*?)(\s*)$", re.IGNORECASE)
NEARBY_QUEST_ROW = re.compile(r"^(\s*)(\d+)\s+(\d+)\s+(.+?)(\s*)$")
NEARBY_DIRECTION_HEADER = re.compile(r"^\s*Dir\s+Nearby (Landmarks|Shops)\s*$", re.IGNORECASE)
NEARBY_DIRECTION_ROW = re.compile(
    r"^(\s*)(N|S|E|W|NE|NW|SE|SW|U|D)\s{2,}(.+?)(\s*)$", re.IGNORECASE
)
DENSE_ITEM_ROW = re.compile(
    r"^(\s*(?:R\s+)?\((?:(?:lvl|tot)\s+)?\s*\d+\)\s*)(.+?)(\s*)$", re.IGNORECASE
)
QUEST_DETAIL_FIELD = re.compile(
    r"^(Quest Name|Location|Area Level|Creator|Editors|Approximate difficulty \(scale from 1 to 10\)|"
    r"General Quest Info|Previous goal short description|Previous goal long description|"
    r"Current goal short description|Current goal long description):\s*(.*?)\s*$",
    re.IGNORECASE,
)
QUEST_DETAIL_LABELS = {
    "quest name": "任務名稱", "location": "地點", "area level": "區域等級",
    "creator": "作者", "editors": "編輯者",
    "approximate difficulty (scale from 1 to 10)": "大約難度（1 到 10）",
    "general quest info": "任務概述",
    "previous goal short description": "之前目標簡述",
    "previous goal long description": "之前目標詳細說明",
    "current goal short description": "目前目標簡述",
    "current goal long description": "目前目標詳細說明",
}
STATUS_SPELL_LINE = re.compile(r"^Spell '([^']+)'(?:,\s*(.*))?$", re.IGNORECASE)
STATUS_STAT_NAMES = {"Str": "力量", "Int": "智力", "Wis": "智慧", "Dex": "敏捷", "Con": "體質", "Chr": "魅力"}
ATTRIBUTE_CHANGE_ZH = {
    "strength": "力量", "intelligence": "智力", "wisdom": "智慧",
    "dex": "敏捷", "con": "體質", "chr": "魅力",
    "spell save": "法術豁免", "fire save": "火焰豁免",
    "cold save": "冰冷豁免", "zap save": "電擊豁免",
    "breath save": "吐息豁免", "poison save": "毒素豁免",
    "physical save": "物理豁免", "hitroll": "命中加值",
    "damage": "傷害加值",
}
PUT_ITEM_LINE = re.compile(r"^(\s*)You put (.+) in (.+)\.(\s*)$", re.IGNORECASE)
GET_FROM_LINE = re.compile(r"^(\s*)You get (.+) from (.+)\.(\s*)$", re.IGNORECASE)
DROP_ITEM_LINE = re.compile(r"^(\s*)You drop (.+)\.(\s*)$", re.IGNORECASE)
GIVE_ITEM_LINE = re.compile(r"^(\s*)You give (.+) to (.+)\.(\s*)$", re.IGNORECASE)
BUY_ITEM_LINE = re.compile(
    r"^(\s*)You buy (.+) from (.+) for (\d[\d,]*) gold coins\.(\s*)$",
    re.IGNORECASE,
)
SEMANTIC_EVENT_PATTERNS = (
    ("blade_spin", re.compile(r"^(\s*)You start swinging and spinning the blade, '([^']+)'\.\.\.(\s*)$", re.I)),
    ("blade_flick_hit", re.compile(r"^(\s*)You flick the blade, '([^']+)' at (.+?), and score a quick hit!(\s*)$", re.I)),
    ("blade_flick_miss", re.compile(r"^(\s*)You flick the blade, '([^']+)', but (.+?) avoids your attack\.(\s*)$", re.I)),
    ("blade_reaction", re.compile(r"^(\s*)(.+?) (looks mildly annoyed|makes a strange noise) as you place the blade, '([^']+)' in (?:his|her|its) back\.(\s*)$", re.I)),
    ("damage_other", re.compile(
        r"^(\s*)(?:kxft)?\s*(.+?)'s (.+?) "
        r"(heals|annoys|scratches|hits|injures|wounds|mauls|decimates|devastates|maims|"
        r"MUTILATES|DISMEMBERS|DISEMBOWELS|MASSACRES|\*\*\* MASSACRES \*\*\*|"
        r"\*\*\* DEVASTATES \*\*\*|\*\*\* OBLITERATES \*\*\*|"
        r"\*\*\* DEMOLISHES \*\*\*|\*\*\* DESTROYS \*\*\*|"
        r"\*\*\* ANNIHILATES \*\*\*) (.+?)([.!])(\s*)$", re.I)),
    ("aura_fades", re.compile(r"^(\s*)The (white|black) aura (?:around|about) (.+?) fades\.(\s*)$", re.I)),
    ("actor_white_aura", re.compile(r"^(\s*)(.+?) is surrounded by a white aura\.(\s*)$", re.I)),
    ("restored_health", re.compile(r"^(\s*)(.+?) restored you to full health!(\s*)$", re.I)),
    ("get_gold", re.compile(r"^(\s*)You get (\d[\d,]*) gold coins?\.(\s*)$", re.I)),
    ("get_gold_from", re.compile(r"^(\s*)You get (\d[\d,]*) gold coins? from (.+)\.(\s*)$", re.I)),
    ("drop_gold", re.compile(r"^(\s*)You drop (\d[\d,]*) gold coins?\.(\s*)$", re.I)),
    ("gives_you", re.compile(r"^(\s*)(.+?) gives you (.+)\.(\s*)$", re.I)),
    ("item_compare", re.compile(r"^(\s*)(.+?) (worse|a bit better|looks better) than (.+?)\.(\s*)$", re.I)),
    ("starts_following_you", re.compile(r"^(\s*)(.+?) starts following you\.(\s*)$", re.I)),
    ("stops_following_you", re.compile(r"^(\s*)(.+?) stops following you\.(\s*)$", re.I)),
    ("you_follow", re.compile(r"^(\s*)You (start|stop) following (.+?)\.(\s*)$", re.I)),
    ("group_add", re.compile(r"^(\s*)You add (.+?) to your group\.(\s*)$", re.I)),
    ("group_member", re.compile(r"^(\s*)(.+?) has become a member of the group\.(\s*)$", re.I)),
    ("group_left", re.compile(r"^(\s*)(.+?) has left the group\.(\s*)$", re.I)),
    ("stops_resting", re.compile(r"^(\s*)(.+?) stops resting, and stands up\.(\s*)$", re.I)),
    ("teleport_vanish", re.compile(r"^(\s*)(.+?) vanishes into a flickering red glow\.(\s*)$", re.I)),
    ("teleport_appear", re.compile(r"^(\s*)(.+?) (?:appears out of a flickering blue glow|appears in the middle of the room)\.(\s*)$", re.I)),
    ("unique_item", re.compile(r"^(\s*)(.+?) \(unique\)(\s*)$", re.I)),
    ("actor_puts", re.compile(r"^(\s*)(.+?) puts (.+?) in (.+)\.(\s*)$", re.I)),
    ("equipment", re.compile(r"^(\s*)You are (wearing|holding|wielding|carrying) (.+)\.(\s*)$", re.I)),
    ("sniffs_air", re.compile(r"^(\s*)(.+?) sniffs the air, as though catching a nearby scent\.(\s*)$", re.I)),
    ("actor_dead", re.compile(r"^(\s*)(.+?) is DEAD!(\s*)$", re.I)),
    ("actor_arrived", re.compile(r"^(\s*)(.+?) has arrived\.(\s*)$", re.I)),
    ("throw_shadow", re.compile(r"^(\s*)You throw (.+?) at (.+?)(, but miss)?!(\s*)$", re.I)),
    ("no_loot", re.compile(r"^(\s*)You see nothing left to loot from the corpse of (.+?)\.(\s*)$", re.I)),
    ("block_attack", re.compile(r"^(\s*)You block (?:his|her|its|their) attack\.(\s*)$", re.I)),
    ("door_action", re.compile(r"^(\s*)You (open|close|lock|unlock) (.+)\.(\s*)$", re.I)),
    ("door_closed", re.compile(r"^(\s*)The (.+) is closed\.(\s*)$", re.I)),
    ("sacrifice_gold", re.compile(r"^(\s*)You receive (\d[\d,]*) gold coins? for your sacrifice of (.+)\.(\s*)$", re.I)),
    ("condition", re.compile(r"^(\s*)You have (a few scratches|some small wounds and bruises|quite a few wounds|big nasty wounds and scratches)\.(\s*)$", re.I)),
    ("physical_reserve", re.compile(r"^(\s*)The physical reserve deep within you feels replenished\.(\s*)$", re.I)),
    ("sense_life", re.compile(r"^(\s*)You sense a hidden life form in the room\.(\s*)$", re.I)),
    ("pray_transport", re.compile(r"^(\s*)You pray to (.+) for transportation\.\.\.(\s*)$", re.I)),
    ("directional_departure", re.compile(r"^(\s*)(.+?) (leaves|flies|walks|runs|departs) (north|south|east|west|northeast|northwest|southeast|southwest|up|down)\.(\s*)$", re.I)),
    ("get_item", re.compile(r"^(\s*)You get (.+)\.(\s*)$", re.I)),
    ("drop_item", re.compile(r"^(\s*)You drop (.+)\.(\s*)$", re.I)),
    ("stop_using", re.compile(r"^(\s*)You stop using (.+)\.(\s*)$", re.I)),
    ("cast_spell", re.compile(r"^(\s*)(.+?) casts '([^']+)'(\s*)$", re.I)),
    ("actor_here", re.compile(r"^(\s*)(.+?) is here\.(\s*)$", re.I)),
    ("actor_darkened", re.compile(r"^(\s*)(.+?) is darkened\.(\s*)$", re.I)),
    ("receive_xp", re.compile(r"^(\s*)You receive (\d[\d,]*(?:\.\d+)?[kKmMbB]?) experience\.(\s*)$", re.I)),
    ("limited_xp", re.compile(r"^(\s*)You (?:don't learn much from this battle, but still|learn very little from this battle\.\s+You|are too high level, but still) receive (\d[\d,]*(?:\.\d+)?[kKmMbB]?) experience\.(\s*)$", re.I)),
    ("gain_favor", re.compile(r"^(\s*)You gain favor in the eyes of (.+)!(\s*)$", re.I)),
    ("achievement", re.compile(r"^(\s*)You have completed the achievement:\s*(.+?)(\s*)$", re.I)),
    ("sacrifice", re.compile(r"^(\s*)(.+?) appreciates your sacrifice of (.+)\.(\s*)$", re.I)),
    ("miss", re.compile(r"^(\s*)(.+?) misses (.+)\.(\s*)$", re.I)),
    ("dodge", re.compile(r"^(\s*)(.+?) dodges (.+?)'s attack\.(\s*)$", re.I)),
    ("mortally_wounded", re.compile(r"^(\s*)(.+?) is mortally wounded, and will die soon if not aided\.(\s*)$", re.I)),
    ("keeps_bleeding", re.compile(r"^(\s*)(.+?) keeps bleeding!(\s*)$", re.I)),
    ("stops_bleeding", re.compile(r"^(\s*)(.+?) stops bleeding\.(\s*)$", re.I)),
    ("anticipates_bloodletting", re.compile(
        r"^(\s*)(.+?) anticipates your bloodletting stab and avoids your attack\.(\s*)$", re.I)),
    ("trip_fly_recovery", re.compile(
        r"^(\s*)(.+?) tries to trip you, but your fly spell helps you recover\.(\s*)$", re.I)),
    ("trip_avoided", re.compile(
        r"^(\s*)(.+?) tries to trip you, but you avoid the move well in advance\.(\s*)$", re.I)),
    ("parry", re.compile(r"^(\s*)(.+?) parries (.+?)'s attack\.(\s*)$", re.I)),
    ("too_weak_to_attack", re.compile(r"^(\s*)(.+?) is too weak to attack\.(\s*)$", re.I)),
    ("collapses_branches", re.compile(
        r"^(\s*)(.+?) collapses in a heap of broken branches\.(\s*)$", re.I)),
    ("sprays_webs", re.compile(r"^(\s*)(.+?) sprays webs all over you!(\s*)$", re.I)),
)
COMBAT_TARGET_PATTERNS = (
    ("stomp_crunch", re.compile(r"^(\s*)You stomp on (.+) and hear something crunch!(\s*)$", re.I)),
    ("stomp_toes", re.compile(r"^(\s*)You stomp on (.+)'s toes!(\s*)$", re.I)),
    ("lunge", re.compile(r"^(\s*)You lunge at (.+)!(\s*)$", re.I)),
    ("evaluate", re.compile(r"^(\s*)You quickly evaluate (.+)'s armor and anatomy\.\.\.(\s*)$", re.I)),
    ("stomp", re.compile(r"^(\s*)You stomp on (.+)!(\s*)$", re.I)),
    ("weapon_display", re.compile(r"^(\s*)You direct the final motions of your weapon display at (.+)\.\.\.(\s*)$", re.I)),
    ("quick_thrust", re.compile(r"^(\s*)You quickly thrust your weapon at (.+)!(\s*)$", re.I)),
    ("draw_thrust", re.compile(r"^(\s*)You draw back your weapon, then thrust it at (.+)!(\s*)$", re.I)),
    ("circle", re.compile(r"^(\s*)You circle behind (.+) and find a perfect opportunity!(\s*)$", re.I)),
    ("downward_thrust", re.compile(
        r"^(\s*)You aim a powerful downward thrust at (.+) in an attempt to finish (?:him|her|it) off!(\s*)$", re.I
    )),
    ("feign", re.compile(r"^(\s*)You feign a sudden attack on (.+), who moves to block!(\s*)$", re.I)),
    ("death_cry", re.compile(r"^(\s*)Your blood freezes as you hear (.+)'s death cry!(\s*)$", re.I)),
    ("slit_throat", re.compile(r"^(\s*)You slit (.+)'s throat\.(\s*)$", re.I)),
    ("dead", re.compile(r"^(\s*)(.+) is DEAD!(\s*)$")),
    ("backstab_damage", re.compile(r"^(\s*)Your backstab does considerable damage to (.+)!(\s*)$", re.I)),
    ("dirt", re.compile(r"^(\s*)You throw dirt in (.+)'s face, blinding (?:him|her|it)!(\s*)$", re.I)),
    ("blade_back", re.compile(
        r"^(\s*)You place the blade, '([^']+)' in the back of (.+), mortally wounding (?:him|her|it)\.(\s*)$", re.I
    )),
)

QUEST_HELP_FIXED_LINES = {
    "Sorry, unknown option for 'quest' command.": "抱歉，quest 指令沒有這個選項。",
    "Quests Help": "任務指令說明",
    "For quests you have already accepted:": "已接受的任務：",
    "To list or accept new quests:": "列出或接受新任務：",
    "To find nearby quests:": "尋找附近的任務：",
    "For quests you have completed:": "已完成的任務：",
    "                          such as Sloe, Kordan, Archais, the mainland,":
        "                          例如 Sloe、Kordan、Archais、mainland、",
    "                          Ramanek or Suboria":
        "                          Ramanek 或 Suboria",
}
QUEST_HELP_DESCRIPTIONS = {
    "show a list of quests you are on": "顯示你正在進行的任務列表",
    "show information about a quest you are on": "顯示進行中任務的資訊",
    "show even more information about a quest": "顯示任務的更多資訊",
    "shows information about your active quest": "顯示目前作用中任務的資訊",
    "change your active quest": "變更目前作用中的任務",
    "show quests on hold or put a quest on hold": "顯示擱置的任務，或將任務擱置",
    "show any quests that are available here": "顯示此處可接受的任務",
    "show some details about a specific quest": "顯示指定任務的部分詳細資訊",
    "accept a given quest from 'quest list'": "接受 quest list 中指定的任務",
    "show any nearby quests": "顯示附近的任務",
    "show info on nearby quests": "顯示附近任務的資訊",
    "show a global list of all available quests": "顯示所有可接受任務的全域列表",
    "show all quests on an island or continent,": "顯示某座島嶼或大陸上的所有任務，",
    "show all completed feats, deeds and legacies": "顯示所有已完成的功績、事蹟與傳承",
    "show a quest's completion string": "顯示任務完成時的文字",
    "show dependent chained quests": "顯示相依的連鎖任務",
}


def translate_inventory_timestamp(text):
    """Translate the fixed label while preserving every timestamp digit."""
    match = INVENTORY_TIMESTAMP.match(str(text).strip())
    if not match:
        return None
    weekday, month, day, clock, year = match.groups()
    return "最新庫存新增時間：%s %s %s %s %s" % (
        WEEKDAY_ZH[weekday], MONTH_ZH[month], day, clock, year
    )


def to_traditional_characters(text):
    """Convert Chinese glyphs with Windows itself; preserve wording and ASCII."""
    value = str(text)
    if not value:
        return value
    try:
        flag = 0x04000000  # LCMAP_TRADITIONAL_CHINESE
        fn = ctypes.windll.kernel32.LCMapStringEx
        fn.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_wchar_p,
                       ctypes.c_int, ctypes.c_wchar_p, ctypes.c_int,
                       ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
        fn.restype = ctypes.c_int
        needed = fn("zh-TW", flag, value, len(value), None, 0, None, None, 0)
        if needed <= 0:
            return value
        output = ctypes.create_unicode_buffer(needed)
        written = fn("zh-TW", flag, value, len(value), output, needed, None, None, 0)
        return output[:written] if written > 0 else value
    except Exception:
        # Character normalization is optional; it must never break translation.
        return value


def structured_block_kind(text):
    """Return a non-skills structured block kind without inspecting its items."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped == "You are carrying:":
            return "inventory"
        if stripped == "The following items are available for sale at this time:":
            return "shop_items"
        if stripped == "The following spell castings may be purchased for a small fee:":
            return "shop_spells"
        if stripped == "The following items are currently up for grabs:":
            return "free_items"
        for marker, kind in STRUCTURED_CONTAINS_MARKERS.items():
            if marker in line:
                return kind
        # Some containers use a descriptive heading instead of the shorter
        # "on ground contains:" marker, for example shelves and tables.  Match
        # the stable grammatical shell, not a particular container name.
        if re.match(r"^\s*\(on ground\)\s+.+?\s+has on it:\s*$", line, re.I):
            return "ground_container"
    # Quiet-period buffering can split a large container or shop listing after
    # its start marker.  Recognize continuation pages by their repeated column
    # shape, never by specific item names.  Allow one trailing summary line.
    nonempty = [line for line in lines if line.strip()]
    if len(nonempty) >= 3:
        required = len(nonempty) - 1
        counted_items = sum(bool(re.match(r"^\s*\(\s*\d+\)", line)) for line in nonempty)
        priced_items = sum(bool(re.match(
            r"^\s*(?:[A-Z]\s+)?\[\s*(?:\d+|Price)\s*\]",
            line,
            re.IGNORECASE,
        )) for line in nonempty)
        if counted_items >= required:
            return "counted_item_continuation"
        if priced_items >= required:
            return "shop_item_continuation"
    return None

def rotate_log_if_needed(path, max_bytes):
    """Archive a full local log without deleting or overwriting old records."""
    try:
        if not path.is_file() or path.stat().st_size < int(max_bytes):
            return None
        LOG_ARCHIVE.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        destination = LOG_ARCHIVE / (path.stem + "_" + stamp + path.suffix)
        serial = 1
        while destination.exists():
            destination = LOG_ARCHIVE / (path.stem + "_" + stamp + "_%02d" % serial + path.suffix)
            serial += 1
        os.replace(path, destination)
        return destination
    except Exception:
        return None


def log(msg, critical=False):
    try:
        if critical or config().get("debug_logging", False):
            rotate_log_if_needed(LOG, WORKER_LOG_MAX_BYTES)
            with LOG.open("a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S")+" [LMT] "+str(msg)+"\n")
    except Exception:
        pass

def config():
    c=DEFAULT.copy()
    try: c.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    except Exception: pass
    return c


def cloud_translation_config():
    """Read the human-editable cloud settings; this does not make network calls."""
    result = CLOUD_TRANSLATION_DEFAULT.copy()
    try:
        values = {}
        for raw_line in CLOUD_CONFIG.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip().lower()] = value.strip()
        service = int(values.get("service", 0))
        result["service"] = service if service in {0, 1, 2, 3} else 0
        result["api_keys"] = {
            1: values.get("azure_api_key", ""),
            2: values.get("google_api_key", ""),
            3: values.get("deepl_api_key", ""),
        }
        # Upgrade compatibility: an older single api_key belongs to the
        # selected primary service.  It is never copied to another provider.
        legacy_key = values.get("api_key", "")
        if legacy_key and result["service"] in result["api_keys"]:
            result["api_keys"][result["service"]] = (
                result["api_keys"][result["service"]] or legacy_key
            )
        result["azure_region"] = values.get("azure_region", "global") or "global"
        result["timeout_seconds"] = max(0.5, min(10.0, float(values.get("timeout_seconds", 1.5))))
        result["allow_private_messages"] = values.get("allow_private_messages", "0") == "1"
    except Exception:
        return CLOUD_TRANSLATION_DEFAULT.copy()
    # service=0 is an explicit master switch.  A selected provider without a
    # key may still fall through to another provider whose key is configured.
    if result["service"] == 0:
        return result
    if not any(result["api_keys"].values()):
        result["service"] = 0
    return result


def is_private_cloud_text(text):
    """Conservatively keep direct/private player communication offline."""
    value = str(text)
    patterns = (
        r"\btells you[,:' ]", r"\bYou tell\b", r"\bwhispers? to you\b",
        r"\bYou whisper\b", r"\bsends you (?:a )?private message\b",
        r"\bprivate message\b",
    )
    return any(re.search(pattern, value, re.I) for pattern in patterns)


def cloud_translation_candidates(text=""):
    settings = cloud_translation_config()
    if settings["service"] == 0:
        return []
    if not settings["allow_private_messages"] and is_private_cloud_text(text):
        return []
    primary = settings["service"]
    order = [primary] + [service for service in (1, 2, 3) if service != primary]
    now = time.monotonic()
    return [
        (service, settings["api_keys"].get(service, ""), settings)
        for service in order
        if settings["api_keys"].get(service, "")
        and service not in CLOUD_DISABLED_FOR_SESSION
        and now >= CLOUD_DISABLED_UNTIL.get(service, 0.0)
    ]


def validate_cloud_translation(source, translated):
    translated = to_traditional_characters(str(translated).strip())
    if not translated or not any("\u3400" <= char <= "\u9fff" for char in translated):
        raise RuntimeError("CLOUD_NO_CHINESE")
    if numeric_values(source) and not numeric_items_preserved(source, translated):
        raise RuntimeError("CLOUD_NUMERIC_ITEMS_MISSING")
    ok, reason = translation_sanity_ok(source, translated)
    if not ok:
        raise RuntimeError("CLOUD_SANITY_" + reason)
    return translated


def mark_translation_engine(name):
    TRANSLATION_ENGINES_USED.add(str(name))


def record_cloud_usage(service, sources):
    """Persist successful request characters; never store text or credentials."""
    try:
        today = time.strftime("%Y-%m-%d")
        month = time.strftime("%Y-%m")
        data = {"started": today, "months": {}}
        if API_USAGE_FILE.is_file():
            loaded = json.loads(API_USAGE_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        months = data.setdefault("months", {})
        current = months.setdefault(month, {})
        key = cloud_translation_client.SERVICE_NAMES.get(service, "unknown")
        current[key] = int(current.get(key, 0)) + sum(len(str(value)) for value in sources)
        atomic_write(API_USAGE_FILE, json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as error:
        log("unable to record local cloud usage: %r" % error, True)


def cloud_api_report():
    """Report every provider without exposing keys or spending translation quota."""
    settings = cloud_translation_config()
    primary = settings.get("service", 0)
    month = time.strftime("%Y-%m")
    started = "this version"
    local = {}
    try:
        data = json.loads(API_USAGE_FILE.read_text(encoding="utf-8"))
        started = str(data.get("started") or started)
        local = data.get("months", {}).get(month, {})
    except Exception:
        pass
    labels = {1: "Microsoft Azure", 2: "Google Cloud", 3: "DeepL"}
    lines = ["%s API 用量報告。本機從 %s 開始計算。" % (month, started)]
    for service in (1, 2, 3):
        name = labels[service]
        key = settings["api_keys"].get(service, "")
        role = " 目前是第一順位。" if primary == service else ""
        if not key:
            lines.append("%s：未設定。%s" % (name, role))
            continue
        local_count = int(local.get(cloud_translation_client.SERVICE_NAMES[service], 0))
        state = "本次執行期間已停用" if service in CLOUD_DISABLED_FOR_SESSION else "已設定"
        if service == 3:
            try:
                usage = cloud_translation_client.deepl_usage(
                    key, max(1.0, min(10.0, settings["timeout_seconds"]))
                )
                used = usage["character_count"]
                limit = usage["character_limit"]
                remaining = max(0, limit - used)
                lines.append(
                    "%s：官方本期已使用 %s／%s 字元，剩餘 %s。"
                    "本機本月送出 %s 字元。%s" %
                    (name, used, limit, remaining, local_count, role)
                )
            except Exception as error:
                lines.append(
                    "%s：%s。官方用量查詢失敗：%s。"
                    "本機本月送出 %s 字元。%s" %
                    (name, state, str(error), local_count, role)
                )
        else:
            lines.append(
                "%s：%s。本機本月送出 %s 字元。"
                "翻譯 API 金鑰無法讀取官方帳戶用量。%s" %
                (name, state, local_count, role)
            )
    return "\n".join(lines)


def cloud_translate_many_partial(sources):
    """Keep valid cloud units and retry only rejected units with the next provider."""
    sources = [str(source) for source in sources]
    results = [None] * len(sources)
    pending = list(range(len(sources)))
    for service, api_key, settings in cloud_translation_candidates("\n".join(sources)):
        if not pending:
            break
        provider = cloud_translation_client.SERVICE_NAMES.get(service, "unknown")
        try:
            translated = cloud_translation_client.translate_many(
                service, [sources[index] for index in pending], api_key,
                settings["azure_region"], settings["timeout_seconds"],
            )
            record_cloud_usage(service, [sources[index] for index in pending])
            if len(translated) != len(pending):
                raise RuntimeError("CLOUD_RESULT_COUNT_MISMATCH")
            unresolved = []
            accepted = 0
            for index, result in zip(pending, translated):
                try:
                    results[index] = validate_cloud_translation(sources[index], result)
                    accepted += 1
                except Exception as unit_error:
                    unresolved.append(index)
                    log("cloud provider=%s unit fallback: %s" % (provider, str(unit_error)), True)
            if accepted:
                mark_translation_engine(provider)
                CLOUD_FAILURE_COUNT[service] = 0
            pending = unresolved
        except Exception as error:
            if cloud_translation_client.is_session_blocking_error(error):
                CLOUD_DISABLED_FOR_SESSION.add(service)
                CLOUD_FAILURE_COUNT[service] = 0
                log("cloud provider=%s disabled for this worker session after provider error: %s" %
                    (provider, str(error)), True)
                continue
            CLOUD_FAILURE_COUNT[service] = CLOUD_FAILURE_COUNT.get(service, 0) + 1
            if CLOUD_FAILURE_COUNT[service] >= CLOUD_FAILURE_LIMIT:
                CLOUD_DISABLED_UNTIL[service] = time.monotonic() + CLOUD_COOLDOWN_SECONDS
                CLOUD_FAILURE_COUNT[service] = 0
                log("cloud provider=%s paused for %d seconds after repeated failures" %
                    (provider, CLOUD_COOLDOWN_SECONDS), True)
            else:
                log("cloud provider=%s fallback: %s" % (provider, str(error)), True)
    return results if any(result is not None for result in results) else None


def cloud_translate_many(sources):
    """Return a complete cloud batch, or let the existing LMT fallback run."""
    results = cloud_translate_many_partial(sources)
    return results if results is not None and all(result is not None for result in results) else None


def load_deterministic_templates():
    """Load only explicitly enabled, reviewed templates; catalog is optional."""
    global DETERMINISTIC_TEMPLATES, DETERMINISTIC_FIELD_GLOSSARY
    if DETERMINISTIC_TEMPLATES is not None:
        return DETERMINISTIC_TEMPLATES
    templates = []
    try:
        uri = STRUCTURE_CATALOG_FILE.resolve().as_uri() + "?mode=ro"
        db = sqlite3.connect(uri, uri=True, timeout=1)
        try:
            rows = db.execute(
                "SELECT source_regex,output_template,category FROM translation_templates "
                "WHERE enabled=1 ORDER BY priority DESC,id"
            ).fetchall()
            glossary_rows = db.execute(
                "SELECT field_name,source_value,translated_value FROM field_glossary"
            ).fetchall()
        finally:
            db.close()
        for source_regex, output_template, category in rows:
            try:
                templates.append((re.compile(source_regex), output_template, category))
            except re.error as error:
                log("ignored invalid deterministic template: %r" % error, True)
        DETERMINISTIC_FIELD_GLOSSARY = {
            (str(field).lower(), str(source).upper()): str(translated)
            for field, source, translated in glossary_rows
        }
    except Exception as error:
        # The catalog is an optional accelerator, never a translation dependency.
        log("structure catalog unavailable: %r" % error, True)
    DETERMINISTIC_TEMPLATES = templates
    if DETERMINISTIC_FIELD_GLOSSARY is None:
        DETERMINISTIC_FIELD_GLOSSARY = {}
    return templates


def deterministic_translate(text):
    """Return a reviewed full-match translation while preserving named fields."""
    source = str(text)
    if "\n" in source or "\r" in source:
        return None
    global GAME_GLOSSARY
    if GAME_GLOSSARY is None:
        try:
            raw = json.loads(GAME_GLOSSARY_FILE.read_text(encoding="utf-8-sig"))
            GAME_GLOSSARY = {str(key): str(value).strip() for key, value in raw.items() if str(value).strip()}
        except Exception as error:
            log("game glossary unavailable: %r" % error, True)
            GAME_GLOSSARY = {}
    if source.strip() in GAME_GLOSSARY:
        return GAME_GLOSSARY[source.strip()]
    # Keep common kobold profession labels stable without teaching the rule to
    # arbitrary prose.  A full noun-phrase match avoids changing proper names
    # or uses of "kobold" elsewhere in room descriptions and dialogue.
    kobold_professions = {
        "warrior": "戰士",
        "mage": "法師",
        "cleric": "牧師",
        "thief": "盜賊",
        "necromancer": "死靈法師",
        "druid": "德魯伊",
    }
    kobold_match = re.fullmatch(
        r"(?:(a|an|the)\s+)?kobold\s+(warrior|mage|cleric|thief|necromancer|druid)",
        source.strip(),
        re.IGNORECASE,
    )
    if kobold_match:
        prefix = "一名" if kobold_match.group(1) else ""
        return "%s狗頭人%s" % (prefix, kobold_professions[kobold_match.group(2).lower()])
    fixed_events = {
        # Mush-Z emits these compact health-condition labels from the prompt.
        # They are status values, not ordinary adjective fragments.
        "excellent": "狀態極佳",
        "scratches": "輕微擦傷",
        "small wounds": "一些小傷口",
        "quite a few": "傷勢不少",
        "big nasty": "嚴重傷勢",
        "pretty hurt": "傷得很重",
        "awful": "傷勢危急",
        "You receive an explorer point!": "你獲得 1 點探索點數！",
        "You receive a combat point!": "你獲得 1 點戰鬥點數！",
        "You receive a profession point!": "你獲得 1 點職業點數！",
        "You have become more renowned!": "你的聲望提高了！",
        "You are full.": "你完全恢復了。",
        "The white aura around your body fades.": "你身旁的白色光環消退了。",
        "The black aura about your body fades.": "你身旁的黑色光環消退了。",
        "Your ice shield fades and is gone.": "你的冰盾消退並消失了。",
        "The magical flames protecting you flicker and go out.": "保護你的魔法火焰閃爍後熄滅了。",
        "Your coat of crystal scales suddenly shatters in a chain reaction!": "你的水晶鱗片外衣突然產生連鎖反應並碎裂！",
        "Your displaced image rejoins your body.": "偏移的影像重新與你的身體重合。",
        "You feel your invisible mana shield flicker and go out.": "你感覺隱形的法力護盾閃爍後消失了。",
        "You feel a slight tingle and you feel somehow abandoned.": "你感到一陣輕微刺麻，彷彿失去了庇護。",
        "You no longer feel sharp and at your best.": "你不再感到敏銳且處於最佳狀態。",
        "You slowly fade into existence.": "你的身影緩緩顯現。",
        "You slowly float down as your fly spell wears off.": "飛行法術消退，你緩緩飄落地面。",
        "You feel less aware of your surroundings.": "你對周遭環境的感知變弱了。",
        "Your body is still too exhausted from last time.": "你的身體仍未從上一次的消耗中恢復。",
        "A shadow decoy melts back into the shadows.": "影子誘餌融回陰影之中。",
        "Your shield of faith dissipates, and you no longer feel as protected by your god.": "你的信仰護盾消散了，你不再感受到神祇的庇護。",
        "You scout out a hiding spot...": "你尋找適合藏身的位置……",
        "Stealth mode on.": "隱密模式已開啟。",
        "You wake up.": "你醒了過來。",
        "You feel as though Shift is watching over you.": "你感覺 Shift 正守護著你。",
        "You do not seem to have that item.": "你似乎沒有那件物品。",
        "Huh?": "什麼？",
        "Thrust at who?": "要刺擊誰？",
        "No-one by that name found.": "找不到那個名字的對象。",
        "You feel slightly sick.": "你感到有些不適。",
        "You gather darkness around yourself.": "你將黑暗聚集在自己周圍。",
        "You wait for an appropriate moment to turn and run, but it never comes...": "你等待轉身逃跑的適當時機，但時機始終沒有出現……",
        "You go to sleep in your hiding place.": "你在藏身處睡下。",
        "The shadows here are not sharp enough for you to target your enemy.": "這裡的陰影不夠鮮明，無法讓你鎖定敵人。",
        "You are already awake...": "你已經醒著了……",
        "You recover your morale!": "你的士氣恢復了！",
        "Your vision slowly returns.": "你的視力逐漸恢復。",
        "It becomes bright enough to see clearly.": "周圍變得明亮，已經可以清楚看見。",
        "Nothing matching those arguments found.": "找不到符合那些條件的項目。",
        "You are too exhausted!": "你太疲憊了！",
        "You begin to recover your morale!": "你的士氣開始恢復！",
        "You sit down and rest your tired bones.": "你坐下來休息疲憊的身體。",
    }
    if source.strip() in fixed_events:
        return fixed_events[source.strip()]
    resource_names = {
        "hp": "血量", "hit": "血量", "hit point": "血量", "hit points": "血量",
        "mana": "法力", "m": "法力",
        "movement": "體力", "move": "體力", "mv": "體力",
    }
    full = re.fullmatch(
        r"(hp|mana|movement)(?:\s+and\s+(hp|mana|movement))?\s+(?:is|are)\s+full\.",
        source, re.I,
    )
    if full:
        names = [resource_names[full.group(1).lower()]]
        if full.group(2):
            names.append(resource_names[full.group(2).lower()])
        return "和".join(names) + "已完全恢復。"
    gain = re.fullmatch(r"([+-]\d+)\s+(hp|hit points?|mana|movement|move|mv)\.", source, re.I)
    if gain:
        return "%s %s。" % (gain.group(1), resource_names[gain.group(2).lower()])
    regen = re.fullmatch(r"You'll need about (.+?) to regen (hp|mana|movement)\.", source, re.I)
    if regen:
        duration = regen.group(1)
        duration = re.sub(r"\b(\d+)\s+hours?\b", r"\1 小時", duration, flags=re.I)
        duration = re.sub(r"\b(\d+)\s+minutes?\b", r"\1 分", duration, flags=re.I)
        duration = re.sub(r"\b(\d+)\s+seconds?\b", r"\1 秒", duration, flags=re.I)
        duration = re.sub(r"\s+and\s+", " ", duration, flags=re.I)
        return "你大約還需要 %s 才能完全恢復%s。" % (
            duration.strip(), resource_names[regen.group(2).lower()],
        )
    combo = translate_combo_line(source)
    if combo is not None:
        return combo
    if re.fullmatch(
        r"You know the following skills:\s+You don't know of any skills by that name\.",
        source,
        re.I,
    ):
        return "你會以下技能：你不知道任何符合該名稱的技能。"
    match = re.fullmatch(r"<\s*(\d+)hp\s+(\d+)m\s+(\d+)mv\s*>", source, re.I)
    if match:
        # Keep the compact unit suffixes because the general numeric guard
        # interprets m as a multiplier; labels make the prompt readable.
        return "<血量 %shp 法力 %sm 體力 %smv>" % match.groups()
    match = re.fullmatch(r"You have (\d+) practices? remaining\.", source, re.I)
    if match:
        return "你還有 %s 點練習點數。" % match.group(1)
    match = re.fullmatch(r"You have (\d+) practices? left\.", source, re.I)
    if match:
        return "你還有 %s 點練習點數。" % match.group(1)
    match = re.fullmatch(r"Armor:\s*([-+]?\d+)\s*\(you are wearing (light|medium|heavy) armor\)", source, re.I)
    if match:
        armor_kind = {"light": "輕甲", "medium": "中甲", "heavy": "重甲"}[match.group(2).lower()]
        return "護甲：%s（你穿著%s）。" % (match.group(1), armor_kind)
    match = re.fullmatch(r"(\d{1,2})\s+(am|pm)", source, re.I)
    if match:
        period = "上午" if match.group(2).lower() == "am" else "下午"
        return "%s %s 點" % (period, match.group(1))
    match = re.fullmatch(r"freak\s+(\d+)!", source, re.I)
    if match:
        # Alter Aeon uses "freak" as a game-specific combat grade. Preserve
        # the term and number locally instead of asking LMT to guess it.
        return "freak %s!" % match.group(1)
    match = re.fullmatch(r"You are level (\d+) ([A-Za-z]+)\.", source, re.I)
    if match:
        class_name = {
            "mage": "法師", "cleric": "牧師", "thief": "盜賊",
            "warrior": "戰士", "necromancer": "死靈法師", "druid": "德魯伊",
        }.get(match.group(2).lower(), match.group(2))
        return "你是 %s 級%s。" % (match.group(1), class_name)
    match = re.fullmatch(r"Your skill level is (.+)\.", source, re.I)
    if match:
        class_names = {
            "mage": "法師", "cleric": "牧師", "thief": "盜賊",
            "warrior": "戰士", "necromancer": "死靈法師", "druid": "德魯伊",
        }
        entries = re.findall(r"level\s+(\d+)\s+([A-Za-z]+)", match.group(1), re.I)
        if entries:
            rendered = ["%s 級%s" % (level, class_names.get(name.lower(), name)) for level, name in entries]
            return "你的技能等級是 %s。" % "、".join(rendered)
    match = re.fullmatch(r"--- Received (\d+) lines, sent (\d+) lines\.", source, re.I)
    if match:
        return "--- 收到 %s 行，送出 %s 行。" % match.groups()
    match = re.fullmatch(
        r"--- Output buffer has (\d+)/(\d+) lines in it \(([\d.]+)% full\)\.",
        source,
        re.I,
    )
    if match:
        return "--- 輸出緩衝區中有 %s/%s 行（已使用 %s%%）。" % match.groups()
    match = re.fullmatch(
        r"--- Matched (\d+) triggers, (\d+) aliases, and (\d+) timers fired\.",
        source,
        re.I,
    )
    if match:
        return "--- 已比對 %s 個觸發器、%s 個別名，並觸發 %s 個計時器。" % match.groups()
    match = re.fullmatch(r"You spend (\d[\d,]*) experience\.\.\.", source, re.I)
    if match:
        return "你花費了 %s 點經驗值……" % match.group(1)
    if source == ("You can use alt-1 through alt-0 to retrieve your last 10 received messages. "
                   "Double clicking the hotkey copies the message to the clipboard. "
                   "Hit it 3 times to paste the message into the input window for reviewing."):
        return ("你可以使用 alt-1 到 alt-0 取回最近 10 則收到的訊息。按兩下快速鍵會將訊息複製到剪貼簿；"
                "按 3 次則會貼到輸入視窗供你檢查。")
    if source == "Type config showtips to disable these tips.":
        return "輸入 config showtips 可停用這些提示。"
    match = re.fullmatch(
        r"Your (strength|intelligence|wisdom|dex|con|chr|spell save|fire save|cold save|"
        r"zap save|breath save|poison save|physical save|hitroll|damage) is now\s+"
        r"([-+]?\d+(?:\.\d+)?%?)",
        source,
        re.I,
    )
    if match:
        return "你的%s現在是 %s。" % (ATTRIBUTE_CHANGE_ZH[match.group(1).lower()], match.group(2))
    match = re.fullmatch(
        r"Armor:\s*([-+]?\d+)\s*\(you are only wearing (\d+) of (\d+) pieces of armor\)",
        source,
        re.I,
    )
    if match:
        armor, worn, total = match.groups()
        return "護甲：%s（你目前只穿戴 %s 個護甲部位中的 %s 個）。" % (armor, total, worn)
    for pattern, output_template, _category in load_deterministic_templates():
        match = pattern.fullmatch(source)
        if not match:
            continue
        raw_values = match.groupdict()
        rendered_values = {}
        for field, value in raw_values.items():
            if value is None:
                rendered_values[field] = value
                continue
            translated = DETERMINISTIC_FIELD_GLOSSARY.get((field.lower(), str(value).upper()))
            if translated is None and field.lower() == "wear":
                tokens = str(value).split()
                translated_tokens = [
                    DETERMINISTIC_FIELD_GLOSSARY.get(("wear", token.upper()), token)
                    for token in tokens
                ]
                translated = "、".join(translated_tokens)
            rendered_values[field] = translated if translated is not None else value
        try:
            result = output_template.format_map(rendered_values)
        except (KeyError, ValueError):
            continue
        # Every captured source value must survive verbatim in the result.
        if any(value is not None and value not in result and rendered_values.get(field) not in result
               for field, value in raw_values.items()):
            continue
        return result
    return None


def translate_combo_line(text):
    """Render attack-combo counters and every bonus without asking the model."""
    source = str(text).strip()
    starts = (
        (r"^You got a (\d+) attack combo!", "你完成了 %s 連擊！"),
        (r"^You successfully finished a full (\d+) attack combo!", "你成功完成完整 %s 連擊！"),
    )
    for pattern, template in starts:
        match = re.match(pattern, source, re.I)
        if not match:
            continue
        output = [template % match.group(1)]
        suffix = source[match.end():]
        bonus_re = re.compile(
            r"\s*(Combo bonus|Completion bonus):\s*([A-Za-z ]+?)\s+by\s+(-?\d+(?:\.\d+)?%?)!",
            re.I,
        )
        position = 0
        for bonus in bonus_re.finditer(suffix):
            if suffix[position:bonus.start()].strip():
                return None
            label, field, value = bonus.groups()
            zh_label = "連擊獎勵" if label.lower().startswith("combo") else "完成獎勵"
            zh_field = BONUS_FIELD_ZH.get(field.strip().lower(), field.strip())
            output.append("%s：%s增加 %s！" % (zh_label, zh_field, value))
            position = bonus.end()
        if suffix[position:].strip():
            return None
        return " ".join(output)
    return None

def session_alive():
    if SESSION_FILE is None: return True
    try: return (time.time()-SESSION_FILE.stat().st_mtime) <= SESSION_MAX_AGE
    except OSError: return False

def process_is_alive(pid):
    if pid <= 0: return False
    try:
        import ctypes
        SYNCHRONIZE=0x00100000
        h=ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE,False,pid)
        if not h: return False
        ctypes.windll.kernel32.CloseHandle(h); return True
    except Exception: return False

def acquire_lock():
    for _ in range(2):
        try:
            fd=os.open(str(LOCK),os.O_CREAT|os.O_EXCL|os.O_WRONLY)
            with os.fdopen(fd,"w",encoding="ascii") as f:f.write(str(os.getpid()))
            return True
        except FileExistsError:
            try:
                t=LOCK.read_text(encoding="ascii").strip()
                if t and process_is_alive(int(t)): return False
            except Exception: pass
            try: LOCK.unlink()
            except Exception: return False
    return False

def cache_connection():
    global CACHE_CONNECTION,CACHE_DISABLED
    if CACHE_DISABLED:return None
    if CACHE_CONNECTION is not None:return CACHE_CONNECTION
    try:
        c=sqlite3.connect(str(CACHE_DB),timeout=2)
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("""CREATE TABLE IF NOT EXISTS translations(
          cache_key TEXT PRIMARY KEY, source_text TEXT NOT NULL, translated_text TEXT NOT NULL,
          source_language TEXT NOT NULL, target_language TEXT NOT NULL, cache_version INTEGER NOT NULL,
          created_at INTEGER NOT NULL,last_used INTEGER NOT NULL,hit_count INTEGER NOT NULL DEFAULT 0)""")
        c.commit();CACHE_CONNECTION=c;return c
    except Exception as e:
        CACHE_DISABLED=True;log("cache disabled: %r"%e,True);return None

def cache_key(text,c):
    v=int(c.get("translation_cache_version",12))
    m="\0".join((str(v),c["source_language"],c["target_language"],text))
    return hashlib.sha256(m.encode("utf-8")).hexdigest(),v

def cache_get(text,c):
    if not c.get("translation_cache_enabled",True):return None
    db=cache_connection()
    if db is None:return None
    try:
        k,_=cache_key(text,c); row=db.execute("SELECT translated_text FROM translations WHERE cache_key=?",(k,)).fetchone()
        if not row:return None
        # Cached output is not automatically trustworthy.  Earlier versions
        # could store a heading-only result as a successful translation.  Run
        # every hit through the current, content-agnostic completeness rules.
        translated = to_traditional_characters(row[0])
        ok, reason = translation_sanity_ok(text, translated)
        if not ok:
            db.execute("DELETE FROM translations WHERE cache_key=?", (k,))
            db.commit()
            log("discarded invalid cached translation: %s" % reason, True)
            return None
        db.execute("UPDATE translations SET translated_text=?,last_used=?,hit_count=hit_count+1 WHERE cache_key=?",
                   (translated,int(time.time()),k));db.commit()
        return translated
    except Exception:return None

def cache_put(text,out,c):
    if not c.get("translation_cache_enabled",True):return
    db=cache_connection()
    if db is None:return
    try:
        out=to_traditional_characters(out)
        k,v=cache_key(text,c);now=int(time.time())
        db.execute("""INSERT OR REPLACE INTO translations
        (cache_key,source_text,translated_text,source_language,target_language,cache_version,created_at,last_used,hit_count)
        VALUES(?,?,?,?,?,?,?,?,COALESCE((SELECT hit_count FROM translations WHERE cache_key=?),0))""",
        (k,text,out,c["source_language"],c["target_language"],v,now,now,k));db.commit()
    except Exception as e:log("cache write failed: %r"%e,True)


def clear_recent_translation_cache(limit=5):
    """Delete recently used translation rows on the owning worker connection."""
    db = cache_connection()
    if db is None:
        raise RuntimeError("CACHE_UNAVAILABLE")
    limit = max(1, min(50, int(limit)))
    rows = db.execute(
        "SELECT cache_key,source_text FROM translations ORDER BY last_used DESC, rowid DESC LIMIT ?",
        (limit,),
    ).fetchall()
    npc_names = set()
    for _cache_key, source_text in rows:
        npc_names.update(npc_names_in_source(source_text, db))
    if rows:
        db.executemany("DELETE FROM translations WHERE cache_key=?", [(row[0],) for row in rows])
        if npc_names:
            # A name lock is derived from translation output, so clearing the
            # triggering translations must also let the player choose it
            # again. Remove every whole-sentence cache mentioning that NPC;
            # otherwise an older sentence could immediately recreate the
            # just-deleted spelling without a new translation.
            all_rows = db.execute("SELECT cache_key,source_text FROM translations").fetchall()
            stale_keys = [
                cache_key for cache_key, source_text in all_rows
                if any(english_name_in_text(name, source_text) for name in npc_names)
            ]
            if stale_keys:
                db.executemany("DELETE FROM translations WHERE cache_key=?", [(key,) for key in stale_keys])
            db.executemany("DELETE FROM npc_name_aliases WHERE source_name=?", [(name,) for name in npc_names])
            db.executemany("DELETE FROM npc_names WHERE source_name=?", [(name,) for name in npc_names])
        db.commit()
    return len(rows)


NPC_SOURCE_SUBJECT = re.compile(
    r"^([A-Z][A-Za-z'’-]*(?:\s+(?:the\s+)?[A-Za-z][A-Za-z'’-]*){0,5})\s+"
    r"(says|asks|yells|whispers|shouts|exclaims|gives|bows|waves|leaves|arrives|"
    r"sighs|starts|stops|has|stretches|concentrates|watches|stands|sits|goes|moves)\b",
    re.I,
)
NPC_TALK_TARGET = re.compile(r"^You try to talk to\s+(.+?)\.{3}\s*$", re.I)
NPC_GROUP_ADD_TARGET = re.compile(r"^You add\s+(.+?)\s+to your group\.\s*$", re.I)
NPC_MAP_TARGET = re.compile(r"^([A-Z][A-Za-z'’-]*(?:\s+[A-Za-z][A-Za-z'’-]*){0,5})\s*->")
NPC_RESULT_MARKERS = {
    "says": r"說道|說", "asks": r"問道|問", "yells": r"大喊|喊道|喊",
    "whispers": r"低語|耳語", "shouts": r"大喊|喊道|喊", "exclaims": r"驚呼|喊道",
    "gives": r"給|交|將", "bows": r"鞠躬", "waves": r"揮", "leaves": r"離開|前往",
    "arrives": r"抵達|來了|到達", "sighs": r"嘆", "starts": r"開始|驚|嚇",
    "has": r"加入|成為|離開", "stops": r"停止",
    "stretches": r"伸展|伸", "concentrates": r"專注|集中", "watches": r"守望|守|看",
    "stands": r"站", "sits": r"坐", "goes": r"回|走|前往", "moves": r"移動|走",
}


def ensure_npc_name_tables(db):
    db.execute("""CREATE TABLE IF NOT EXISTS npc_names(
      source_name TEXT PRIMARY KEY, translated_name TEXT NOT NULL, updated_at INTEGER NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS npc_name_aliases(
      source_name TEXT NOT NULL, alias_name TEXT NOT NULL,
      PRIMARY KEY(source_name,alias_name))""")


def npc_source_identity(line):
    """Return a stable English NPC identity and its grammatical context."""
    value = str(line).strip()
    talk = NPC_TALK_TARGET.match(value)
    if talk:
        return talk.group(1).strip(), "talk"
    group_add = NPC_GROUP_ADD_TARGET.match(value)
    if group_add:
        return group_add.group(1).strip(), "group_add"
    mapped = NPC_MAP_TARGET.match(value)
    if mapped:
        return mapped.group(1).strip(), "map"
    subject = NPC_SOURCE_SUBJECT.match(value)
    if not subject:
        return None
    name, verb = subject.groups()
    first = name.split()[0].lower()
    if first in {"a", "an", "the", "you", "your"}:
        return None
    return name.strip(), verb.lower()


def npc_names_in_source(source, db=None):
    """Find directly structured names plus already-known names in a request."""
    value = str(source)
    names = set()
    for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        identity = npc_source_identity(line)
        if identity:
            names.add(identity[0].lower())
    try:
        db = db or cache_connection()
        if db is not None:
            ensure_npc_name_tables(db)
            for (name,) in db.execute("SELECT source_name FROM npc_names"):
                if english_name_in_text(name, value):
                    names.add(name)
    except Exception:
        pass
    return names


def english_name_in_text(name, text):
    return re.search(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(str(name)), str(text), re.I) is not None


def translated_npc_span(line, context):
    """Locate only the translated name field; fail closed on uncertain prose."""
    value = str(line)
    if context == "talk":
        match = re.match(r"^(?:你|您).*?(?:和|跟)(.{1,40}?)(?=說話|交談|談談)", value)
        return match.span(1) if match else None
    if context == "map":
        match = re.match(r"^\s*(.{1,40}?)\s*(?=->)", value)
        return match.span(1) if match else None
    if context == "group_add":
        match = re.match(r"^\s*你將(.{1,40}?)(?=加入隊伍)", value)
        return match.span(1) if match else None
    marker = NPC_RESULT_MARKERS.get(context)
    if not marker:
        return None
    match = re.match(r"^\s*(.{1,40}?)(?=" + marker + r")", value)
    return match.span(1) if match else None


def valid_npc_translation(value):
    value = str(value).strip()
    if not value or len(value) > 40 or re.search(r"[\r\n，。！？,:：；;]", value):
        return False
    return bool(re.search(r"[A-Za-z\u3400-\u9fff]", value))


def normalize_npc_names(source, translated):
    """Keep each locally encountered NPC spelling stable across all engines."""
    db = cache_connection()
    if db is None:
        return translated
    try:
        ensure_npc_name_tables(db)
        source_lines = str(source).replace("\r\n", "\n").replace("\r", "\n").split("\n")
        result_lines = str(translated).replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if len(source_lines) == len(result_lines):
            for index, source_line in enumerate(source_lines):
                identity = npc_source_identity(source_line)
                if not identity:
                    continue
                english_name, context = identity
                key = english_name.lower()
                span = translated_npc_span(result_lines[index], context)
                if not span:
                    continue
                candidate = result_lines[index][span[0]:span[1]].strip()
                if not valid_npc_translation(candidate):
                    continue
                row = db.execute("SELECT translated_name FROM npc_names WHERE source_name=?", (key,)).fetchone()
                canonical = row[0] if row else candidate
                now = int(time.time())
                if row is None:
                    db.execute("INSERT INTO npc_names(source_name,translated_name,updated_at) VALUES(?,?,?)",
                               (key, canonical, now))
                else:
                    db.execute("UPDATE npc_names SET updated_at=? WHERE source_name=?", (now, key))
                db.execute("INSERT OR IGNORE INTO npc_name_aliases(source_name,alias_name) VALUES(?,?)",
                           (key, candidate))
                result_lines[index] = result_lines[index][:span[0]] + canonical + result_lines[index][span[1]:]
        result = "\n".join(result_lines)
        # Once an alias has been observed in a structured line, normalize it
        # inside other cached prose whenever the corresponding English name is
        # present in the source. This repairs old sentence caches lazily.
        for key, canonical in db.execute("SELECT source_name,translated_name FROM npc_names"):
            if not english_name_in_text(key, source):
                continue
            for (alias,) in db.execute("SELECT alias_name FROM npc_name_aliases WHERE source_name=?", (key,)):
                if alias and alias != canonical:
                    result = result.replace(alias, canonical)
        db.commit()
        return result
    except Exception as error:
        log("npc name normalization skipped: %r" % error, True)
        return translated

def find_runtime():
    home=Path.home()
    roots=[
        ROOT/"lmt_runtime",
        ROOT,
        home/"Downloads"/"LMT60_1.7B_HOME_DOWNLOADER",
    ]
    server=model=None
    for r in roots:
        if not r.exists(): continue
        if server is None:
            hits=list((r/"tools").rglob("llama-server.exe")) if (r/"tools").exists() else []
            if hits: server=hits[0]
        if model is None:
            q=r/"gguf"/"LMT-60-1.7B-Q4_K_M.gguf"
            if q.is_file(): model=q
    if not server: raise RuntimeError("llama-server.exe not found. Keep LMT60_1.7B_HOME_DOWNLOADER in Downloads, or copy tools into translation_bridge/lmt_runtime.")
    if not model: raise RuntimeError("LMT-60-1.7B-Q4_K_M.gguf not found. Keep it in Downloads\\LMT60_1.7B_HOME_DOWNLOADER\\gguf, or copy gguf into translation_bridge/lmt_runtime.")
    return server,model


def find_runtime_candidates():
    runtime = ROOT / "lmt_runtime"
    model = runtime / "gguf" / "LMT-60-1.7B-Q4_K_M.gguf"
    if not model.is_file():
        _server, model = find_runtime()
    candidates = []
    vulkan = runtime / "backends" / "vulkan" / "llama-server.exe"
    cpu = runtime / "tools" / "llama-server.exe"
    if vulkan.is_file():
        candidates.append(("vulkan", vulkan, model, 99))
    if cpu.is_file():
        candidates.append(("cpu", cpu, model, 0))
    if not candidates:
        server, model = find_runtime()
        candidates.append(("cpu", server, model, 0))
    return candidates

def http_get(path,timeout=1):
    with urllib.request.urlopen("http://127.0.0.1:%d%s"%(PORT,path),timeout=timeout) as r:return r.read()

def http_post(path,obj,timeout):
    if path in ("/completion", "/v1/chat/completions") and not SERVER_READY:
        start_server()
    data=json.dumps(obj,ensure_ascii=False).encode("utf-8")
    req=urllib.request.Request("http://127.0.0.1:%d%s"%(PORT,path),data=data,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode("utf-8","replace"))

def backend_fingerprint(candidates):
    parts=[platform.node().lower(), "cpu-autotune-v%d"%CPU_AUTOTUNE_VERSION,
           "logical-cpus:%s"%(os.cpu_count() or 0)]
    for backend,server,model,gpu_layers in candidates:
        for path in (server,model):
            try:
                stat=path.stat();parts.append("%s:%s:%s"%(str(path),stat.st_size,stat.st_mtime_ns))
            except OSError:parts.append("%s:missing"%path)
        parts.append("%s:%s"%(backend,gpu_layers))
    return hashlib.sha256("\n".join(parts).encode("utf-8","replace")).hexdigest()

def load_backend_choice(candidates):
    try:
        data=json.loads(BACKEND_CHOICE_FILE.read_text(encoding="utf-8"))
        if data.get("fingerprint") != backend_fingerprint(candidates):return None
        selected=str(data.get("backend") or "")
        if any(item[0] == selected for item in candidates):
            threads=data.get("threads")
            threads_batch=data.get("threads_batch")
            if threads is not None:
                threads=int(threads)
                if threads < 1 or threads > (os.cpu_count() or 1):return None
                threads_batch=int(threads_batch or threads)
                if threads_batch < 1 or threads_batch > (os.cpu_count() or 1):return None
            return {"backend":selected,"threads":threads,
                    "threads_batch":threads_batch}
    except Exception:pass
    return None

def save_backend_choice(candidates,selection,scores,metrics=None):
    try:
        backend=selection["backend"]
        data={"fingerprint":backend_fingerprint(candidates),"machine":platform.node(),
              "backend":backend,"threads":selection.get("threads"),
              "threads_batch":selection.get("threads_batch"),
              "scores_tokens_per_second":scores,"updated_at":int(time.time())}
        if metrics:data["benchmark_metrics"]=metrics
        tmp=BACKEND_CHOICE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        os.replace(tmp,BACKEND_CHOICE_FILE)
    except Exception as e:log("backend choice save failed: %r"%e,True)

def stop_candidate(candidate):
    global ACTIVE_CANDIDATE
    if candidate is None:return
    try:candidate.terminate();candidate.wait(timeout=3)
    except Exception:
        try:candidate.kill();candidate.wait(timeout=2)
        except Exception:pass
    if ACTIVE_CANDIDATE is candidate:
        ACTIVE_CANDIDATE = None

def launch_candidate(item,sf,threads=None,threads_batch=None):
    global ACTIVE_CANDIDATE
    if SERVER_SHUTTING_DOWN:
        raise RuntimeError("worker shutdown requested")
    backend,server,model,gpu_layers=item
    flags=getattr(subprocess,"CREATE_NO_WINDOW",0)
    profile=("default" if threads is None else "t%d-tb%d"%(threads,threads_batch or threads))
    log("trying backend=%s profile=%s llama-server=%s model=%s"%(backend,profile,server,model),True)
    sf.write("\n=== BACKEND %s PROFILE %s ===\n" % (backend,profile));sf.flush()
    cmd=[str(server),"-m",str(model),"--host","127.0.0.1","--port",str(PORT),
         "--ctx-size","4096","--parallel","1","--gpu-layers",str(gpu_layers),
         "--reasoning","off","--no-warmup","--log-colors","off"]
    if threads is not None:
        cmd.extend(["--threads",str(threads),"--threads-batch",str(threads_batch or threads)])
    candidate=subprocess.Popen(cmd,stdout=sf,stderr=subprocess.STDOUT,creationflags=flags)
    ACTIVE_CANDIDATE = candidate
    deadline=time.time()+15
    while time.time()<deadline:
        if SERVER_SHUTTING_DOWN:
            stop_candidate(candidate)
            raise RuntimeError("worker shutdown requested")
        if candidate.poll() is not None:raise RuntimeError("process exited during startup")
        try:http_get("/health",1);break
        except Exception:time.sleep(.15)
    else:raise RuntimeError("startup timeout")
    warm=http_post("/completion",{
        "prompt":"Translate English to Chinese.\nEnglish: Ready\nChinese:",
        "n_predict":8,"temperature":0.0,"stream":False},20)
    if not (warm.get("content") or "").strip():raise RuntimeError("warm-up returned blank output")
    ACTIVE_CANDIDATE = None
    return candidate

def benchmark_candidate(runs=2):
    prompt=("Translate the following English text into Traditional Chinese.\nEnglish: "
            "The old guard points toward the eastern gate. Patients at the town hospital are "
            "getting worse, and the administrator needs evidence before nightfall.\nTraditional Chinese:")
    samples=[];prompt_samples=[];total_samples=[]
    for _ in range(max(1,runs)):
        started=time.perf_counter()
        response=http_post("/completion",{
            "prompt":prompt,"n_predict":96,"temperature":0.0,
            "repeat_penalty":1.1,"repeat_last_n":64,"stream":False},25)
        elapsed=max(.001,time.perf_counter()-started)
        content=(response.get("content") or "").strip()
        tokens=int(response.get("tokens_predicted") or 0)
        if tokens < 4 or not content or not re.search(r"[\u3400-\u9fff]",content):
            raise RuntimeError("invalid benchmark output")
        timings=response.get("timings") or {}
        decode=float(timings.get("predicted_per_second") or 0)
        if decode <= 0:decode=tokens/elapsed
        samples.append(decode);total_samples.append(elapsed)
        prompt_speed=float(timings.get("prompt_per_second") or 0)
        if prompt_speed > 0:prompt_samples.append(prompt_speed)
    return {"decode_tps":round(median(samples),2),
            "prompt_tps":round(median(prompt_samples),2) if prompt_samples else None,
            "elapsed_seconds":round(median(total_samples),3)}

def cpu_thread_profiles():
    logical=max(1,os.cpu_count() or 1)
    return [value for value in (2,4,6,8,12,16) if value <= logical]

def profile_key(backend,threads):
    return backend if threads is None else "%s-t%d"%(backend,threads)

def benchmark_profile(item,sf,threads=None,threads_batch=None):
    candidate=None
    try:
        candidate=launch_candidate(item,sf,threads,threads_batch)
        return benchmark_candidate()
    finally:
        stop_candidate(candidate);time.sleep(.15)

def _start_server_impl():
    global SERVER_PROCESS, SERVER_BACKEND, SERVER_THREADS
    # Reuse a server already answering on our private port.
    try:
        http_get("/health",.5); log("reusing llama-server on port %d"%PORT,True); return
    except Exception: pass
    sf=open(SERVER_LOG,"w",encoding="utf-8",errors="replace")
    candidates=find_runtime_candidates()
    force_benchmark = FORCE_BACKEND_BENCHMARK_FILE.is_file()
    if force_benchmark:
        try: FORCE_BACKEND_BENCHMARK_FILE.unlink()
        except OSError: pass
    selection=None if force_benchmark else load_backend_choice(candidates)
    allow_autotune = SERVER_ALLOW_AUTOTUNE or force_benchmark
    if selection is None and not allow_autotune:
        # Offline-first users must be able to translate immediately even on a
        # very slow computer.  Prefer the portable CPU backend and let
        # llama.cpp choose its own conservative thread defaults.
        safe_item=next((item for item in candidates if item[0] == "cpu"),candidates[0])
        selection={"backend":safe_item[0],"threads":None,"threads_batch":None}
        save_backend_choice(candidates,selection,{},
                            {"startup_mode":"safe_default_no_benchmark"})
        log("no backend profile; using safe %s default without benchmark"%safe_item[0],True)
    elif selection is None:
        scores={};metrics={};base_metrics={}
        for item in candidates:
            if SERVER_SHUTTING_DOWN: raise RuntimeError("worker shutdown requested")
            try:
                result=benchmark_profile(item,sf)
                base_metrics[item[0]]=result;metrics[item[0]]=result
                scores[item[0]]=result["decode_tps"]
                log("backend benchmark %s=%.2f decode tokens/sec"%(item[0],scores[item[0]]),True)
            except Exception as e:log("backend benchmark %s failed: %r"%(item[0],e),True)
        if scores:
            cpu_item=next((item for item in candidates if item[0] == "cpu"),None)
            cpu_default=scores.get("cpu",0);vulkan_score=scores.get("vulkan",0)
            best_cpu_threads=None;best_cpu_score=cpu_default
            # A clearly faster GPU makes a CPU sweep pure startup delay.  Tune only
            # CPU-first machines, while retaining llama.cpp's default as a control.
            if cpu_item and (not vulkan_score or cpu_default >= vulkan_score*.5):
                logical=max(1,os.cpu_count() or 1)
                for threads in cpu_thread_profiles():
                    if SERVER_SHUTTING_DOWN: raise RuntimeError("worker shutdown requested")
                    key=profile_key("cpu",threads)
                    try:
                        result=benchmark_profile(cpu_item,sf,threads,logical)
                        metrics[key]=result;scores[key]=result["decode_tps"]
                        log("CPU profile t=%d tb=%d benchmark=%.2f decode tokens/sec"%
                            (threads,logical,scores[key]),True)
                        if scores[key] > best_cpu_score:
                            best_cpu_score=scores[key];best_cpu_threads=threads
                    except Exception as e:log("CPU profile t=%d failed: %r"%(threads,e),True)
                if best_cpu_threads is not None and best_cpu_score < cpu_default*CPU_AUTOTUNE_MIN_GAIN:
                    log("CPU profile gain below %.0f%%; keeping llama.cpp default"%
                        ((CPU_AUTOTUNE_MIN_GAIN-1)*100),True)
                    best_cpu_threads=None;best_cpu_score=cpu_default
            if best_cpu_score > vulkan_score:
                selection={"backend":"cpu","threads":best_cpu_threads,
                           "threads_batch":max(1,os.cpu_count() or 1) if best_cpu_threads else None}
            else:
                selection={"backend":"vulkan","threads":None,"threads_batch":None}
            save_backend_choice(candidates,selection,scores,metrics)
            selected_profile=profile_key(selection["backend"],selection.get("threads"))
            log("backend benchmark selected=%s"%selected_profile,True)
    selected_backend=selection.get("backend") if selection else None
    ordered=sorted(candidates,key=lambda item:0 if item[0] == selected_backend else 1)
    errors=[]
    for item in ordered:
        if SERVER_SHUTTING_DOWN: raise RuntimeError("worker shutdown requested")
        candidate=None
        try:
            threads=selection.get("threads") if selection and item[0] == selected_backend else None
            threads_batch=selection.get("threads_batch") if threads is not None else None
            candidate=launch_candidate(item,sf,threads,threads_batch)
            SERVER_PROCESS=candidate;SERVER_BACKEND=item[0];SERVER_THREADS=threads
            profile=profile_key(item[0],threads)
            log("llama-server READY backend=%s"%profile,True);return
        except Exception as e:
            errors.append("%s: %r"%(item[0],e));log("backend %s unavailable; falling back: %r"%(item[0],e),True)
            stop_candidate(candidate)
            # A tuned profile is optional.  If its flags fail for any reason,
            # retry the same CPU executable with llama.cpp defaults before
            # considering another backend.
            if item[0] == "cpu" and selection and selection.get("threads") is not None:
                candidate=None
                try:
                    candidate=launch_candidate(item,sf)
                    SERVER_PROCESS=candidate;SERVER_BACKEND="cpu";SERVER_THREADS=None
                    log("llama-server READY backend=cpu-default (tuned profile fallback)",True);return
                except Exception as fallback_error:
                    errors.append("cpu-default: %r"%fallback_error)
                    log("CPU default profile unavailable: %r"%fallback_error,True)
                    stop_candidate(candidate)
    raise RuntimeError("all llama-server backends failed: " + "; ".join(errors))


def start_server():
    """Start LMT once; other threads wait while background tuning is active."""
    global SERVER_READY, SERVER_STARTING, SERVER_START_ERROR, SERVER_START_OWNER
    if SERVER_READY:
        return
    current_thread = threading.get_ident()
    with SERVER_START_LOCK:
        if SERVER_READY:
            return
        if SERVER_STARTING:
            starter = False
        else:
            SERVER_STARTING = True
            SERVER_START_ERROR = None
            SERVER_START_OWNER = current_thread
            SERVER_START_EVENT.clear()
            starter = True
    if not starter:
        # Completion calls made by the tuning thread itself must reach the
        # candidate server instead of waiting on their own startup event.
        if SERVER_START_OWNER == current_thread:
            return
        while not SERVER_START_EVENT.wait(0.1):
            if SERVER_SHUTTING_DOWN:
                raise RuntimeError("worker shutdown requested")
        if SERVER_START_ERROR is not None:
            raise RuntimeError("LMT startup failed: %s" % SERVER_START_ERROR)
        return
    try:
        _start_server_impl()
        SERVER_READY = True
    except Exception as error:
        SERVER_START_ERROR = error
        raise
    finally:
        SERVER_STARTING = False
        SERVER_START_OWNER = None
        SERVER_START_EVENT.set()


def start_server_in_background():
    try:
        start_server()
        log("background LMT startup ready", True)
    except Exception as error:
        if not SERVER_SHUTTING_DOWN:
            log("background LMT startup failed: %r" % error, True)

NUMERIC_MULTIPLIERS = {
    "": Decimal(1), "k": Decimal(1000), "m": Decimal(1000000), "b": Decimal(1000000000),
}
NUMERIC_PATTERN = re.compile(r"(?<![A-Za-z])([-+]?\d[\d,]*(?:\.\d+)?)([kKmMbB]?)(%?)(?!_)")


def numeric_values(value):
    output = []
    for number, suffix, percent in NUMERIC_PATTERN.findall(str(value)):
        try:
            amount = Decimal(number.replace(",", "")) * NUMERIC_MULTIPLIERS[suffix.lower()]
            output.append((amount, bool(percent)))
        except (InvalidOperation, KeyError):
            pass
    return output


def numeric_items_preserved(source, translated):
    remaining = numeric_values(translated)
    for number in numeric_values(source):
        try:
            remaining.remove(number)
        except ValueError:
            return False
    return True


def translation_sanity_ok(source, translated):
    s = " ".join(str(source).split())
    t = " ".join(str(translated).split())
    if not t:
        return False, "blank"
    leakage_patterns = (
        r"(?:將|将)所有文字翻(?:譯|译)(?:成|為|为)",
        r"保留(?:正確|正确).{0,20}(?:數字|数字).{0,20}(?:百分比)",
        r"不要(?:省略|刪減|删减).{0,20}(?:總結|总结).{0,20}(?:重複|重复)",
        # The model sometimes translates/paraphrases the instruction itself
        # instead of the game text.  Match its semantic shape rather than one
        # exact wording so unseen variants are rejected too.
        r"保留.{0,12}(?:名字|名稱|名称|姓名).{0,20}(?:不要|不得).{0,10}(?:添加|加入|增加).{0,8}(?:解釋|解释|說明|说明)",
        r"preserve.{0,20}(?:proper\s+)?names?.{0,30}(?:do\s+not|don't).{0,15}(?:add|include).{0,15}explanations?",
    )
    if any(re.search(pattern, t, re.IGNORECASE) for pattern in leakage_patterns):
        return False, "prompt_leakage"
    # Compact rewards are gameplay data. Accept equivalent formatting such as
    # 14k -> 14,000, but reject magnitude changes such as 232k -> 23.2k.
    xp_pattern_en = re.compile(r"([+-]?\d[\d,]*(?:\.\d+)?)([kKmMbB]?)\s*(?:xp|experience)\b", re.I)
    xp_pattern_zh = re.compile(r"([+-]?\d[\d,]*(?:\.\d+)?)([kKmMbB]?)\s*(?:點?經驗(?:值|點)?|xp|experience)\b", re.I)
    def xp_values(pattern, value):
        output = []
        for number, suffix in pattern.findall(value):
            try:
                output.append(Decimal(number.replace(",", "")) * NUMERIC_MULTIPLIERS[suffix.lower()])
            except (InvalidOperation, KeyError):
                pass
        return output
    source_xp = xp_values(xp_pattern_en, s)
    if source_xp:
        translated_xp = xp_values(xp_pattern_zh, t)
        if source_xp != translated_xp[:len(source_xp)]:
            return False, "xp_value_changed_or_missing"
    if len(s) >= 220 and len(t) < 24:
        return False, "catastrophic_undertranslation"
    if len(s) >= 500 and len(t) < 45:
        return False, "severe_undertranslation"
    source_lines = [q.strip() for q in str(source).splitlines() if q.strip()]
    translated_lines = [q.strip() for q in str(translated).splitlines() if q.strip()]
    if is_nearby_map_listing(source) and len(source_lines) != len(translated_lines):
        return False, "nearby_map_line_count_mismatch"
    # Old whole-quest cache entries may contain all of the text but collapse
    # section boundaries into one line. Require every source label to appear
    # at the start of its own translated line. A rejected cache row is deleted
    # by cache_get(), then rebuilt by the structured quest renderer.
    if re.search(r"^Quest Name:\s*", str(source), re.MULTILINE | re.IGNORECASE):
        required_quest_labels = []
        for source_line in str(source).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            match = QUEST_DETAIL_FIELD.match(source_line.strip())
            if match:
                required_quest_labels.append(QUEST_DETAIL_LABELS[match.group(1).lower()])
        for label in required_quest_labels:
            if not any(line.startswith(label + "：") for line in translated_lines):
                return False, "quest_section_labels_missing_or_merged"
    if (is_quest_list_block(source) or is_job_list_block(source)) and len(source_lines) != len(translated_lines):
        return False, "task_list_line_count_mismatch"
    if (is_nearby_direction_listing(source) or is_dense_item_table(source)) and len(source_lines) != len(translated_lines):
        return False, "tabular_line_count_mismatch"
    block_kind = structured_block_kind(source)
    if block_kind and len(source_lines) != len(translated_lines):
        return False, block_kind + "_line_count_mismatch"
    # Quest prose and daily-task wording are intentionally regrouped by the
    # quest renderer. They are not room/NPC display rows, even when several
    # source lines happen to end in punctuation.
    quest_shape = is_quest_structured_block(source)
    independent_start = None if quest_shape else trailing_independent_row_start(source)
    if independent_start is not None:
        required_lines = 1 + len(str(source).replace("\r\n", "\n").replace("\r", "\n").split("\n")[independent_start:])
        if len(translated_lines) < required_lines:
            return False, "trailing_display_rows_merged"
    if len(source_lines) >= 4 and len(s) >= 180 and len(t) < 32:
        return False, "multiline_body_missing"
    # Chinese is normally more compact than English, but a result containing
    # less than roughly a quarter of a substantive source is almost always a
    # translated heading followed by omitted content.  This deliberately uses
    # only shape and length, so it also protects unseen rooms, signs, quests,
    # conversations, and future structured blocks.
    length_ratio = len(t) / max(1, len(s))
    # Short English display-wrapped fragments can legitimately compress below
    # 22% in Chinese.  Keep a conservative 18% floor here; longer blocks retain
    # the stricter thresholds below, so a missing room title/body still causes
    # repair instead of being accepted.
    if len(s) >= 60 and length_ratio < 0.18:
        return False, "substantive_content_missing"
    # For short paragraphs, fluent Chinese commonly uses only 20-25% of the
    # English character count.  Keep the severe 18% floor above, but do not
    # reject complete three-sentence messages merely for natural compression.
    # Blocks of 300+ characters retain the stricter 28% guard below.
    if len(s) >= 120 and length_ratio < 0.20:
        return False, "low_length_ratio"
    # A multi-line source introduced by a colon cannot validly translate to
    # another dangling colon: the payload after the heading has disappeared.
    if len(source_lines) >= 2 and source_lines[0].endswith((':', '：')) and t.endswith((':', '：')):
        return False, "multiline_payload_missing"
    # LMT can stop cleanly after translating only a heading.  Absolute length
    # checks miss larger, but still badly truncated, list output.
    if len(s) >= 300 and length_ratio < 0.28:
        source_sentence_marks = len(re.findall(r"[.!?]+(?=\s|$)", s))
        translated_sentence_marks = len(re.findall(r"[。！？.!?]+", t))
        sentence_coverage = (
            source_sentence_marks >= 2 and
            translated_sentence_marks >= max(2, (source_sentence_marks + 1) // 2)
        )
        # A complete Chinese rendering can naturally fall below 28% of the
        # English character count.  Sentence coverage distinguishes that from
        # the known title-only/premature-EOS failure without weakening the 20%
        # substantive-content floor.
        if not (sentence_coverage and length_ratio >= 0.20):
            return False, "low_length_ratio"
    # Numeric menu/list data is semantic content, not prose the model may omit.
    # Compare numeric *values*, not spelling: the deterministic XP renderer and
    # fluent Chinese may legitimately expand 475k to 475,000.  The old textual
    # comparison rejected that safe equivalent and caused a whole mixed combat
    # + ground-container block to fall back to English.
    source_numbers = numeric_values(s)
    if (len(source_numbers) >= 3 or (block_kind and source_numbers)) and not numeric_items_preserved(s, t):
        return False, "numeric_items_missing"
    # Detect the pathological decoder loop without rejecting normal repeated
    # words.  Three consecutive copies of a 12+ character phrase are not a
    # legitimate translation unless the game itself emitted the same complete
    # line that many times (for example, four identical chairs in a room).
    compact = re.sub(r"\s+", "", t)
    repeated_phrases = re.finditer(r"(.{12,80}?)\1\1", compact)
    # Runs of dashes and other table decoration are normal MUD output, not a
    # decoder loop.  Only language-bearing or numeric repeated units count.
    repeated_phrase = next(
        (match for match in repeated_phrases
         if re.search(r"[A-Za-z0-9\u3400-\u9fff]", match.group(1))),
        None,
    )
    def max_line_repeats(lines):
        counts = {}
        for line in lines:
            counts[line] = counts.get(line, 0) + 1
        return max(counts.values()) if counts else 0
    source_repeat_max = max_line_repeats(source_lines)
    translated_repeat_max = max_line_repeats(translated_lines)
    # Old cache entries created before the repeated-line pipeline could keep
    # only one copy of several identical NPC/object rows.  Such output is not
    # a decoder loop, so the check below did not reject it.  Require repeated
    # substantive source rows to survive with the same multiplicity; a stale
    # collapsed cache entry will then be deleted and rebuilt by the current
    # repeated-line pipeline.
    substantive_source_counts = {}
    for line in source_lines:
        if len(re.sub(r"\s+", "", line)) >= 12:
            substantive_source_counts[line] = substantive_source_counts.get(line, 0) + 1
    # Structured blocks are already rebuilt one source row at a time and the
    # exact line-count check above catches collapsed cache entries.  Comparing
    # repetition again can falsely reject a valid inventory when distinct item
    # names happen to receive the same Chinese rendering.
    if not block_kind and max(substantive_source_counts.values(), default=0) >= 2:
        if translated_repeat_max < max(substantive_source_counts.values()):
            return False, "repeated_source_items_missing"
    legitimate_line_repetition = (
        source_repeat_max >= 3 and
        translated_repeat_max == source_repeat_max
    )
    if repeated_phrase and not legitimate_line_repetition:
        return False, "repetition_loop"
    return True, ""

def completion_once(text, c, n_predict=384, force_robust=False, force_simple=False):
    mark_translation_engine("lmt_q4")
    # LMT was trained and documented with this Standard Translation Prompt.
    # The primary request uses the GGUF's own chat template.  force_simple is
    # retained as the raw-completion fallback flag for older callers.
    prompt = OFFICIAL_PROMPT_TEMPLATE.format(text=text)
    timeout=max(3,float(c.get("request_timeout_seconds",25)))
    if force_simple:
        resp=http_post("/completion",{
            "prompt":prompt,
            "n_predict":n_predict,
            "temperature":0.0,
            "repeat_penalty":1.1,
            "repeat_last_n":128,
            "stream":False,
        },timeout)
        out=(resp.get("content") or "").strip()
        tokens=int(resp.get("tokens_predicted") or 0)
    else:
        resp=http_post("/v1/chat/completions",{
            "messages":[{"role":"user","content":prompt}],
            "max_tokens":n_predict,
            "temperature":0.0,
            "repeat_penalty":1.1,
            "stream":False,
        },timeout)
        choices=resp.get("choices") or []
        if not choices:
            raise RuntimeError("LMT_CHAT_NO_CHOICES")
        out=((choices[0].get("message") or {}).get("content") or "").strip()
        tokens=int((resp.get("usage") or {}).get("completion_tokens") or 0)
    if tokens >= n_predict:
        raise RuntimeError("LMT_TOKEN_LIMIT")
    ok, reason = translation_sanity_ok(text, out)
    if not ok:
        raise RuntimeError("LMT_SANITY_" + reason)
    return out


OUTGOING_DIRECT_CHANNELS = frozenset({
    "arena", "auction", "bovine", "chat", "gossip", "newbie", "xp", "zt",
})
OUTGOING_MESSAGE_COMMANDS = frozenset({"say", "reply", "gtell", "ctell"})


def parse_outgoing_chat_command(command):
    """Split a known talk command without guessing at gameplay commands."""
    command = str(command or "")
    if not command.strip():
        return None
    patterns = (
        r"^(?P<prefix>\s*\$[a-z][a-z0-9_-]*\s+)(?P<message>\S.*)$",
        r"^(?P<prefix>\s*#\s*)(?P<message>\S.*)$",
        r"^(?P<prefix>\s*%send\s+[a-z][a-z0-9_-]*\s+)(?P<message>\S.*)$",
        r"^(?P<prefix>\s*(?:channel|chan)\s+send\s+[a-z][a-z0-9_-]*\s+)(?P<message>\S.*)$",
        r"^(?P<prefix>\s*tell\s+\S+\s+)(?P<message>\S.*)$",
        r"^(?P<prefix>\s*sayto\s+\S+\s+)(?P<message>\S.*)$",
        r"^(?P<prefix>\s*'\s*)(?P<message>\S.*)$",
    )
    for pattern in patterns:
        match = re.match(pattern, command, re.I)
        if match:
            return match.group("prefix"), match.group("message")
    match = re.match(
        r"^(?P<name>[a-z][a-z0-9_-]*)(?P<space>\s+)(?P<message>\S.*)$",
        command, re.I,
    )
    if not match:
        return None
    name = match.group("name").lower()
    if name not in OUTGOING_MESSAGE_COMMANDS and name not in OUTGOING_DIRECT_CHANNELS:
        return None
    return match.group("name") + match.group("space"), match.group("message")


def contains_cjk(text):
    return bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", str(text)))


def protect_outgoing_ascii_terms(text):
    terms = []

    def replace(match):
        terms.append(match.group(0))
        return "ZXQTERM%04dQXZ" % (len(terms) - 1)

    protected = re.sub(
        r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_'’-]*(?:[ \t]+[A-Za-z][A-Za-z0-9_'’-]*)*",
        replace, str(text),
    )
    return protected, terms


def restore_outgoing_ascii_terms(text, terms):
    text = str(text)
    for index, term in enumerate(terms):
        marker = "ZXQTERM%04dQXZ" % index
        if text.count(marker) != 1:
            raise RuntimeError("OUTGOING_PROTECTED_TERM_MISSING_OR_REPEATED")
        text = text.replace(marker, term)
    if re.search(r"ZXQTERM\d{4}QXZ", text):
        raise RuntimeError("OUTGOING_UNKNOWN_PROTECTED_TERM")
    return text


def outgoing_translation_sanity_ok(source, translated):
    translated = str(translated or "").strip()
    if not translated:
        return False, "blank"
    if contains_cjk(translated):
        return False, "chinese_remains"
    if re.search(r"Translate the following|Chinese\s*:|English\s*:", translated, re.I):
        return False, "prompt_leakage"
    compact = re.sub(r"\s+", "", translated)
    if re.search(r"(.{12,80}?)\1\1", compact):
        return False, "repetition_loop"
    if len(str(source)) >= 80 and len(translated) < 12:
        return False, "severe_undertranslation"
    return True, ""


def outgoing_command_may_be_private(command):
    value = str(command or "").lstrip().lower()
    if re.match(r"^(?:tell|reply|gtell|ctell)\b", value):
        return True
    # Alter Aeon permits user-created private channels. Their privacy cannot be
    # inferred from the command text, so generic channel forms stay offline
    # unless the player explicitly allows private-message cloud translation.
    return value.startswith(("$", "#", "%send ", "channel send ", "chan send "))


def cloud_translate_outgoing_message(text, command):
    settings = cloud_translation_config()
    if settings["service"] == 0:
        return None
    if not settings["allow_private_messages"] and outgoing_command_may_be_private(command):
        return None
    for service, api_key, candidate_settings in cloud_translation_candidates(""):
        provider = cloud_translation_client.SERVICE_NAMES.get(service, "unknown")
        try:
            results = cloud_translation_client.translate_many_zh_en(
                service, [text], api_key,
                candidate_settings["azure_region"], candidate_settings["timeout_seconds"],
            )
            record_cloud_usage(service, [text])
            if len(results) != 1:
                raise RuntimeError("CLOUD_ZH_EN_RESULT_COUNT_MISMATCH")
            result = str(results[0]).strip()
            ok, reason = outgoing_translation_sanity_ok(text, result)
            if not ok:
                raise RuntimeError("CLOUD_ZH_EN_SANITY_" + reason)
            mark_translation_engine(provider + "_zh_en")
            CLOUD_FAILURE_COUNT[service] = 0
            return result
        except Exception as error:
            if cloud_translation_client.is_session_blocking_error(error):
                CLOUD_DISABLED_FOR_SESSION.add(service)
                CLOUD_FAILURE_COUNT[service] = 0
                log("outgoing cloud provider=%s disabled for session: %s" %
                    (provider, str(error)), True)
                continue
            CLOUD_FAILURE_COUNT[service] = CLOUD_FAILURE_COUNT.get(service, 0) + 1
            if CLOUD_FAILURE_COUNT[service] >= CLOUD_FAILURE_LIMIT:
                CLOUD_DISABLED_UNTIL[service] = time.monotonic() + CLOUD_COOLDOWN_SECONDS
                CLOUD_FAILURE_COUNT[service] = 0
                log("outgoing cloud provider=%s paused after repeated failures" % provider, True)
            else:
                log("outgoing cloud provider=%s fallback: %s" % (provider, str(error)), True)
    return None


def completion_zh_en_once(text, c):
    """Use LMT's official Standard Translation Prompt in the reverse direction."""
    mark_translation_engine("lmt_q4_zh_en")
    start_server()
    prompt = "Translate the following text from Chinese into English:\nChinese: %s\nEnglish:" % text
    timeout = max(3, float(c.get("request_timeout_seconds", 25)))
    response = http_post("/v1/chat/completions", {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 192,
        "temperature": 0.0,
        "repeat_penalty": 1.1,
        "stream": False,
    }, timeout)
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError("LMT_ZH_EN_NO_CHOICES")
    output = ((choices[0].get("message") or {}).get("content") or "").strip()
    tokens = int((response.get("usage") or {}).get("completion_tokens") or 0)
    if tokens >= 192:
        raise RuntimeError("LMT_ZH_EN_TOKEN_LIMIT")
    ok, reason = outgoing_translation_sanity_ok(text, output)
    if not ok:
        raise RuntimeError("LMT_ZH_EN_SANITY_" + reason)
    return output


def translate_outgoing_chat(command, c=None, completion_func=None):
    """Translate only the message and return a preview command; never send it."""
    parsed = parse_outgoing_chat_command(command)
    if parsed is None:
        raise RuntimeError("OUTGOING_UNSUPPORTED_CHAT_COMMAND")
    prefix, message = parsed
    if not contains_cjk(message):
        raise RuntimeError("OUTGOING_NO_CHINESE_TEXT")
    protected, terms = protect_outgoing_ascii_terms(message)
    reverse_config = dict(c or config())
    reverse_config["source_language"] = "zh"
    reverse_config["target_language"] = "en"
    reverse_config["translation_cache_version"] = 1
    cache_source = CONTROL_TRANSLATE_OUTGOING_CHAT + protected
    output = cache_get(cache_source, reverse_config)
    if output is None:
        if completion_func is not None:
            output = completion_func(protected, reverse_config)
        else:
            output = cloud_translate_outgoing_message(protected, command)
            if output is None:
                output = completion_zh_en_once(protected, reverse_config)
        ok, reason = outgoing_translation_sanity_ok(protected, output)
        if not ok:
            raise RuntimeError("OUTGOING_SANITY_" + reason)
        cache_put(cache_source, output, reverse_config)
    restored = restore_outgoing_ascii_terms(output, terms).replace("\r", " ").replace("\n", " ").strip()
    ok, reason = outgoing_translation_sanity_ok(message, restored)
    if not ok:
        raise RuntimeError("OUTGOING_FINAL_SANITY_" + reason)
    return prefix + restored


def split_source(text, target_chars=650):
    """Split on source lines, preserving order and every non-empty line."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    chunks, current = [], []
    for line in lines:
        candidate = "\n".join(current + [line])
        if current and len(candidate) > target_chars:
            chunks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("\n".join(current))
    return [chunk for chunk in chunks if chunk.strip()]


def semantic_display_chunks(text):
    """Rejoin MUD display wrapping so fallback never translates half a sentence."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    chunks, current = [], []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                chunks.append(" ".join(current))
                current = []
            continue
        current.append(stripped)
        if re.search(r"[.!?][\"')\]]*\s*$", stripped):
            chunks.append(" ".join(current))
            current = []
    if current:
        chunks.append(" ".join(current))
    return chunks


def semantic_sentence_chunks(text):
    """Return complete prose sentences while repairing MUD display wrapping."""
    normalized = " ".join(
        line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if line.strip()
    )
    if not normalized:
        return []
    chunks, start = [], 0
    for match in re.finditer(r"[.!?。！？]+[\"'”’』】）)\]]*", normalized):
        value = normalized[start:match.end()].strip()
        if value:
            chunks.append(value)
        start = match.end()
    tail = normalized[start:].strip()
    if tail:
        chunks.append(tail)
    return chunks


def room_title_index(rows):
    """Find a room title even when movement/status text precedes it."""
    for index, row in enumerate(rows[:-1]):
        if not row or len(row) > 100 or re.search(r"[.!?:;。！？：；]$", row):
            continue
        if re.match(r"^(?:you|your|there|exits?|mobs?|level|experience)\b", row, re.I):
            continue
        following = rows[index + 1]
        if len(following) >= len(row) + 8 or re.search(r"[.!?。！？]$", following):
            return index
    return -1


def room_semantic_chunks(text):
    """Keep movement, room title and complete prose sentences separate."""
    rows = [
        line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if line.strip()
    ]
    if not rows:
        return []
    title_index = room_title_index(rows)
    if title_index < 0:
        return semantic_sentence_chunks(text)
    prefix = semantic_sentence_chunks(" ".join(rows[:title_index]))
    title = rows[title_index]
    body = semantic_sentence_chunks(" ".join(rows[title_index + 1:]))
    return prefix + [title] + body


ROOM_UNIT_MARKER = re.compile(r"(?:\[\[ROOM_(\d+)\]\]|【房[间間]\s*(\d+)】)")
ROOM_UNIT_END_MARKER = re.compile(r"(?:\[\[ROOM_END\]\]|【房[间間](?:结束|結束)】)\s*$")
FIELD_UNIT_MARKER = re.compile(r"\[\[FIELD_(\d+)\]\]")
FIELD_UNIT_END_MARKER = re.compile(r"\[\[FIELD_END\]\]\s*$")


def parse_numbered_room_translation(text, expected_count):
    """Extract marker-delimited translations without trusting model line breaks."""
    value = str(text).strip()
    matches = list(ROOM_UNIT_MARKER.finditer(value))
    if len(matches) != expected_count:
        return None
    output = [None] * expected_count
    for position, match in enumerate(matches):
        index = int(match.group(1) or match.group(2))
        if index < 0 or index >= expected_count or output[index] is not None:
            return None
        end = matches[position + 1].start() if position + 1 < len(matches) else len(value)
        translated = value[match.end():end].strip(" \t\r\n:-")
        translated = ROOM_UNIT_END_MARKER.sub("", translated).strip()
        if not translated:
            return None
        output[index] = " ".join(translated.splitlines()).strip()
    return output if all(output) else None


def translate_room_units_once(chunks, c):
    """Translate each room unit independently; LMT does not reliably retain markers."""
    parsed = []
    for source in chunks:
        result = completion_once(source, c, 256, len(source) >= 180, True)
        result = " ".join(result.splitlines()).strip()
        ok, reason = translation_sanity_ok(source, result)
        if not ok:
            raise RuntimeError("ROOM_UNIT_SANITY_" + reason)
        if not any("\u3400" <= char <= "\u9fff" for char in result):
            raise RuntimeError("ROOM_UNIT_UNTRANSLATED")
        parsed.append(result)
    return parsed


def translate_numbered_fields_once(fields, c):
    """Translate multiple semantic fields in one local-model request."""
    marked = "\n".join("[[FIELD_%d]] %s" % (index, value) for index, value in enumerate(fields))
    prompt = (
        "Translate every numbered English name or phrase into Chinese. Preserve every "
        "[[FIELD_n]] marker exactly and output [[FIELD_END]] after the final translation. "
        "Preserve proper names, digits and punctuation. Do not omit, merge, repeat or explain.\n"
        "English:\n%s\n[[FIELD_END]]\nChinese:" % marked
    )
    mark_translation_engine("lmt_q4")
    timeout = max(3, float(c.get("request_timeout_seconds", 25)))
    response = http_post("/v1/chat/completions", {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
        "temperature": 0.0,
        "repeat_penalty": 1.1,
        "stream": False,
    }, timeout)
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError("FIELD_UNIT_NO_CHOICES")
    value = ((choices[0].get("message") or {}).get("content") or "").strip()
    matches = list(FIELD_UNIT_MARKER.finditer(value))
    if len(matches) != len(fields):
        raise RuntimeError("FIELD_UNIT_MARKERS_MISSING")
    output = [None] * len(fields)
    for position, match in enumerate(matches):
        index = int(match.group(1))
        if index < 0 or index >= len(fields) or output[index] is not None:
            raise RuntimeError("FIELD_UNIT_MARKERS_INVALID")
        end = matches[position + 1].start() if position + 1 < len(matches) else len(value)
        translated = value[match.end():end].strip(" \t\r\n:-")
        translated = FIELD_UNIT_END_MARKER.sub("", translated).strip()
        if not translated:
            raise RuntimeError("FIELD_UNIT_EMPTY")
        translated = " ".join(translated.splitlines()).strip()
        ok, reason = translation_sanity_ok(fields[index], translated)
        if not ok:
            raise RuntimeError("FIELD_UNIT_SANITY_" + reason)
        output[index] = translated
    if not all(output):
        raise RuntimeError("FIELD_UNIT_INCOMPLETE")
    return output


def is_room_prose_candidate(text):
    """Conservatively identify a long narrative room, not arbitrary dialogue."""
    value = str(text).replace("\r\n", "\n").replace("\r", "\n")
    rows = [line.strip() for line in value.split("\n") if line.strip()]
    if len(value) < 180 or len(rows) < 3:
        return False
    if room_title_index(rows) < 0:
        return False
    if re.search(r"\b(?:says|asks|tells|exclaims|yells|whispers),?\s*['\"]", value, re.I):
        return False
    return sum(
        1 for chunk in semantic_sentence_chunks(value)
        if re.search(r"[.!?。！？]", chunk)
    ) >= 2


def seed_room_sentence_cache(source, translated, c):
    """Learn only one-to-one, independently sane sentence pairs."""
    source_chunks = semantic_sentence_chunks(source)
    translated_chunks = semantic_sentence_chunks(translated)
    if len(source_chunks) < 2 or len(source_chunks) != len(translated_chunks):
        return 0
    pairs = []
    for source_chunk, translated_chunk in zip(source_chunks, translated_chunks):
        ok, _ = translation_sanity_ok(source_chunk, translated_chunk)
        if not ok:
            return 0
        pairs.append((source_chunk, translated_chunk))
    for source_chunk, translated_chunk in pairs:
        cache_put(source_chunk, translated_chunk, c)
    return len(pairs)


def translate_room_prose_cached(text, c):
    """Reuse known room sentences without slowing an entirely new room."""
    chunks = room_semantic_chunks(text)
    if len(chunks) < 2:
        return translate_piece(text, c, force_robust=len(text) >= 180)
    cached = [cache_get(chunk, c) for chunk in chunks]
    missing_indexes = [index for index, value in enumerate(cached) if value is None]
    if missing_indexes:
        missing_sources = [chunks[index] for index in missing_indexes]
        translated_missing = cloud_translate_many_partial(missing_sources)
        if translated_missing is None:
            try:
                translated_missing = translate_room_units_once(missing_sources, c)
            except Exception as error:
                # This is a presentation optimisation.  If a model changes or
                # drops a marker, retain the proven whole-room translation path.
                log("room aligned translation fallback: %r" % error, True)
                return translate_piece(text, c, force_robust=True)
        else:
            unresolved = [index for index, value in enumerate(translated_missing) if value is None]
            if unresolved:
                try:
                    local_results = translate_room_units_once(
                        [missing_sources[index] for index in unresolved], c
                    )
                    for index, value in zip(unresolved, local_results):
                        translated_missing[index] = value
                except Exception as error:
                    log("room partial cloud fallback: %r" % error, True)
                    return translate_piece(text, c, force_robust=True)
        for index, translated_chunk in zip(missing_indexes, translated_missing):
            ok, reason = translation_sanity_ok(chunks[index], translated_chunk)
            if not ok:
                log("room aligned translation fallback: %s" % reason, True)
                return translate_piece(text, c, force_robust=True)
            translated_chunk = " ".join(translated_chunk.splitlines()).strip()
            cache_put(chunks[index], translated_chunk, c)
            cached[index] = translated_chunk

    result = "\n".join(value for value in cached if value and value.strip())
    ok, reason = translation_sanity_ok(text, result)
    if not ok:
        raise RuntimeError("ROOM_SENTENCE_CACHE_SANITY_" + reason)
    return result


def reviewed_phrase_translation(text):
    """Return a reviewed reusable game phrase without consulting any model."""
    global PHRASE_GLOSSARY
    if PHRASE_GLOSSARY is None:
        try:
            raw = json.loads(PHRASE_GLOSSARY_FILE.read_text(encoding="utf-8-sig"))
            PHRASE_GLOSSARY = {str(key).strip().lower(): str(value).strip()
                               for key, value in raw.items() if str(value).strip()}
        except Exception as error:
            log("phrase glossary unavailable: %r" % error, True)
            PHRASE_GLOSSARY = {}
    return PHRASE_GLOSSARY.get(str(text).strip().lower())


def translate_piece(text, c, depth=0, force_robust=False, force_simple=False, allow_cloud=True):
    reviewed_phrase = reviewed_phrase_translation(text)
    if reviewed_phrase:
        return reviewed_phrase
    deterministic = deterministic_translate(text)
    if deterministic is not None:
        return deterministic
    if allow_cloud and depth == 0:
        cloud_result = cloud_translate_many([text])
        if cloud_result is not None:
            return cloud_result[0]
    try:
        return completion_once(text, c, 384, force_robust, force_simple)
    except Exception as error:
        if not force_simple:
            # Retry the same complete block with the official raw STP before
            # splitting.  This catches any chat-template-specific failure.
            return translate_piece(text, c, depth + 1, False, True, False)
        # When a model translates only the heading of a short multi-line
        # message, character-sized chunking is the wrong repair: it can split
        # words while still hiding which line vanished.  Translate each
        # non-empty source line independently, preserve blank lines and order,
        # then let the caller validate the reconstructed block as a whole.
        source_lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if depth < 5 and sum(1 for line in source_lines if line.strip()) >= 2:
            semantic_chunks = semantic_display_chunks(text)
            if len(semantic_chunks) >= 2:
                return "\n".join(
                    translate_piece(chunk, c, depth + 1, False, True, False)
                    for chunk in semantic_chunks
                )
        # A failed whole block is retried as smaller ordered pieces.  This is
        # bounded so a hostile/model-looping input cannot recurse forever.
        if depth >= 5 or len(text) < 80:
            numbered = re.match(r"^(\s*\d+\)\s*)(.+)$", text, re.DOTALL)
            if numbered:
                return numbered.group(1) + completion_once(numbered.group(2), c, 128, force_robust, force_simple)
            raise
        chunks = split_source(text, max(90, len(text) // 2))
        if len(chunks) < 2:
            midpoint = len(text) // 2
            left = text.rfind(" ", 0, midpoint)
            if left < 20:
                left = midpoint
            chunks = [text[:left], text[left:]]
        return "\n".join(translate_piece(chunk, c, depth + 1, force_robust, force_simple, False) for chunk in chunks if chunk.strip())


def has_repeated_source_lines(text):
    """Return true when the game emitted the same substantive row twice.

    Two identical NPCs or objects are common in room output.  Sending both
    rows through one prose request lets the model legitimately-looking but
    incorrectly collapse them into one.  Blank, decorative and short rows are
    ignored; exact matching prevents ordinary repeated words from triggering
    this path.
    """
    counts = {}
    for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip()
        if len(re.sub(r"\s+", "", stripped)) < 12:
            continue
        counts[stripped] = counts.get(stripped, 0) + 1
    return any(count >= 2 for count in counts.values())


def trailing_independent_row_start(text):
    """Return the first trailing display row, or None.

    Alter Aeon room prose is display-wrapped: continuation lines usually begin
    after a line without terminal punctuation.  NPCs and visible objects are
    then emitted as complete, independent lines.  Walk backward only while
    both the row and its predecessor are complete, so wrapped narrative stays
    together while the room's trailing entities retain their line boundaries.
    """
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(lines) < 2:
        return None

    def complete(line):
        stripped = line.strip()
        return (
            len(re.sub(r"\s+", "", stripped)) >= 12
            and re.search(r"[.!?]['\"\)\]]*$", stripped) is not None
        )

    start = len(lines)
    for index in range(len(lines) - 1, 0, -1):
        if not complete(lines[index]) or not complete(lines[index - 1]):
            break
        start = index
    return start if start < len(lines) else None


def has_trailing_independent_rows(text):
    return trailing_independent_row_start(text) is not None


def has_deterministic_lines(text):
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return len(lines) >= 2 and any(
        deterministic_translate(line.strip()) is not None
        or semantic_event_match(line) is not None
        or action_template_match(line) is not None
        or combat_template_match(line) is not None
        for line in lines if line.strip()
    )


def translate_mixed_deterministic_block(text, c):
    """Route known lines locally and translate only the remaining contiguous text."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    prefetch_semantic_event_fields(lines, c)
    output, model_buffer = [], []

    def flush_model_buffer():
        if not model_buffer:
            return
        block = "\n".join(model_buffer)
        try:
            output.append(translate_piece(block, c, force_robust=len(block) >= 180))
        except Exception as error:
            log("mixed fragment fallback: %r" % error, True)
            repaired = []
            for chunk in semantic_display_chunks(block):
                try:
                    repaired.append(translate_piece(
                        chunk, c, depth=1, force_robust=len(chunk) >= 180,
                        force_simple=True, allow_cloud=False,
                    ))
                except Exception as chunk_error:
                    log("mixed unit fallback: %r source=%r" % (chunk_error, chunk[:160]), True)
                    repaired.append(chunk)
            output.append("\n".join(repaired))
        model_buffer[:] = []

    for line in lines:
        stripped = line.strip()
        deterministic = deterministic_translate(stripped) if stripped else None
        if semantic_event_match(line) is not None:
            flush_model_buffer()
            try:
                rendered_event = translate_semantic_event_line(line, c)
                if numeric_values(line) and not numeric_items_preserved(line, rendered_event):
                    raise RuntimeError("mixed_semantic_event_numeric_items_missing")
                output.append(rendered_event)
            except Exception as error:
                log("mixed semantic-event fallback: %r source=%r" % (error, line[:160]), True)
                output.append(line)
            continue
        if action_template_match(line) is not None:
            flush_model_buffer()
            try:
                rendered_action = translate_action_line(line, c)
                if numeric_values(line) and not numeric_items_preserved(line, rendered_action):
                    raise RuntimeError("mixed_action_numeric_items_missing")
                output.append(rendered_action)
            except Exception as error:
                log("mixed action-template fallback: %r source=%r" % (error, line[:160]), True)
                output.append(line)
            continue
        if combat_template_match(line) is not None:
            flush_model_buffer()
            try:
                rendered_combat = translate_combat_template_line(line, c)
                if numeric_values(line) and not numeric_items_preserved(line, rendered_combat):
                    raise RuntimeError("mixed_combat_template_numeric_items_missing")
                output.append(rendered_combat)
            except Exception as error:
                log("mixed combat-template fallback: %r source=%r" % (error, line[:160]), True)
                output.append(line)
            continue
        numeric_tokens = numeric_values(stripped)
        if deterministic is None and numeric_tokens:
            flush_model_buffer()
            try:
                translated_line = translate_piece(stripped, c, force_robust=True)
                if not numeric_items_preserved(stripped, translated_line):
                    raise RuntimeError("numeric_line_items_missing")
                output.append(translated_line)
            except Exception as error:
                log("numeric line fallback: %r source=%r" % (error, stripped[:160]), True)
                output.append(line)
            continue
        if deterministic is None:
            model_buffer.append(line)
            continue
        flush_model_buffer()
        indent = line[:len(line) - len(line.lstrip())]
        output.append(indent + deterministic)
    flush_model_buffer()
    result = "\n".join(output)
    ok, reason = translation_sanity_ok(text, result)
    if not ok:
        raise RuntimeError("MIXED_FINAL_SANITY_" + reason)
    return result


def is_numeric_report_block(text):
    """Recognize item comparison/detail reports by stable shape, not names."""
    lines = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    if not lines:
        return False
    if len(lines) >= 2 and lines[0].startswith("Comparing objects "):
        return True
    return any(", Level:" in line and ", Type:" in line for line in lines)


ITEM_AFFECT_CODES = (
    "ATTACK_SPEED", "CLER_CAST_LEVEL", "CLERIC_CAST_LEVEL", "THIEF_SKILL_LEVEL",
    "MAGE_CAST_LEVEL", "NECR_CAST_LEVEL", "WARR_SKILL_LEVEL", "WARRIOR_SKILL_LEVEL",
    "DRUID_CAST_LEVEL", "SAVING_FIRE", "SAVING_COLD", "SAVING_ZAP",
    "SAVING_SPELL", "SAVING_POISON", "SAVING_BREATH", "DAMROLL", "HITROLL",
    "MOV_REGEN", "MOVE_REGEN", "HP_REGEN", "MANA_REGEN", "ALIGNMENT",
    "SPELL_RES", "ABSORB_MAGIC", "ABSORB_FIRE", "ABSORB_ICE", "ABSORB_ZAP",
    "CAST_ABILITY", "HIT_POINTS", "HP", "MOVE", "MV", "MOVEMENT", "MANA", "WIS", "INT", "CON",
    "CHR", "STR", "DEX", "SHIELD_BLOCK", "PARRY", "DODGE", "SNEAK", "HIDE",
    "AGE", "AGING", "SIZE", "LUCK", "ARMOR",
)
ITEM_WEAR_CODES = (
    "HELD", "WEAPON", "HEAD", "NECK", "ARMS", "WRIST", "HANDS", "FINGERS",
    "BODY", "ON_BODY", "ABOUT_BODY", "WAIST", "LEGS", "FEET", "SHIELD", "2_WIELD",
)
ITEM_DETAIL_FIELD_BOUNDARY = re.compile(
    r",\s*(?=(?:Level|Comp|Type|Weight|AC|Damage|Speed|Damage Type|Quality):"
    r"|\d+\s+wield strength(?:\b|$)|(?:" + "|".join(ITEM_AFFECT_CODES) + r")\s+by\b"
    r"|(?:" + "|".join(ITEM_WEAR_CODES) + r")(?:\b|$)|This item\b|Spells? on wearer:)",
    re.I,
)

ITEM_FIELD_LABELS_ZH = {
    "level": "等級", "comp": "材質", "type": "類型", "weight": "重量",
    "ac": "護甲值", "damage": "傷害", "speed": "速度",
    "damage type": "傷害類型", "quality": "品質",
}
ITEM_DAMAGE_WORDS_ZH = {
    "nonorm": "非標準", "toxic": "毒性", "ice": "寒冰", "acidic": "酸性",
    "fire": "火焰", "zapping": "電擊", "slash": "斬擊", "slice": "切割",
    "stab": "刺擊", "pierce": "穿刺", "crush": "壓碎", "pound": "重擊",
    "claw": "爪擊", "bite": "咬擊", "chop": "劈砍",
}


def split_item_detail_fields(line):
    """Split a dense identify row only at known field boundaries."""
    value = str(line).strip()
    if ", Level:" not in value or ", Type:" not in value:
        return None
    fields = [field.strip(" ,") for field in ITEM_DETAIL_FIELD_BOUNDARY.split(value)]
    fields = [field for field in fields if field]
    return fields if len(fields) >= 4 else None


def item_glossary_value(field, value):
    load_deterministic_templates()
    return DETERMINISTIC_FIELD_GLOSSARY.get((field.lower(), str(value).strip().upper()))


def translate_item_detail_field(field, c):
    source = str(field).strip(" ,")
    affect = re.fullmatch(
        r"(" + "|".join(ITEM_AFFECT_CODES) + r")\s+by\s+(minus\s+)?([-+]?\d+(?:\.\d+)?%?)",
        source,
        re.I,
    )
    if affect:
        code, minus, value = affect.groups()
        name = item_glossary_value("affect", code) or code
        return "%s：%s %s" % (name, "減少" if minus else "增加", value)
    wield = re.fullmatch(r"(\d+)\s+wield strength", source, re.I)
    if wield:
        return "持握力量需求：%s" % wield.group(1)
    wear = item_glossary_value("wear", source)
    if wear:
        return "穿戴部位：%s" % wear
    label = re.fullmatch(r"([A-Za-z ]+):\s*(.*)", source)
    if label:
        raw_label, value = label.groups()
        key = raw_label.lower()
        zh_label = ITEM_FIELD_LABELS_ZH.get(key, raw_label)
        if key == "comp":
            parts = [item_glossary_value("composition", token) or token for token in value.split(",")]
            value = "、".join(part.strip() for part in parts)
        elif key == "type":
            value = item_glossary_value("item_type", value) or value
        elif key == "speed":
            value = item_glossary_value("speed", value) or value
        elif key == "quality":
            value = item_glossary_value("quality", value) or value
        elif key == "damage type":
            value = " ".join(ITEM_DAMAGE_WORDS_ZH.get(token.lower(), token) for token in value.split())
        elif key == "weight":
            match = re.fullmatch(r"([-+]?\d+(?:\.\d+)?)\s*(.*)", value)
            if match and match.group(2):
                flags = [item_glossary_value("flag", token) or token for token in match.group(2).split()]
                value = "%s；旗標：%s" % (match.group(1), "、".join(flags))
        return "%s：%s" % (zh_label, value)
    fixed = deterministic_translate(source)
    if fixed is not None:
        return fixed
    return translate_piece(source, c, force_robust=True)


def translate_item_detail_line(line, c):
    fields = split_item_detail_fields(line)
    if not fields:
        return None
    output = []
    for field in fields:
        cache_source = "ITEM_FIELD_V%d:%s" % (STRUCTURED_FIELD_CACHE_VERSION, field)
        translated = cache_get(cache_source, c)
        if translated is None:
            translated = translate_item_detail_field(field, c)
            cache_put(cache_source, translated, c)
        output.append(translated)
    result = "\n".join(output)
    if not numeric_items_preserved(line, result):
        raise RuntimeError("ITEM_DETAIL_NUMERIC_ITEMS_MISSING")
    return result


def translate_numeric_report_block(text, c):
    """Translate reports per line; one bad numeric line cannot discard all rows."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output = []
    for line in lines:
        stripped = line.strip()
        indent = line[:len(line) - len(line.lstrip())]
        if not stripped:
            output.append("")
            continue
        item_detail = translate_item_detail_line(stripped, c)
        if item_detail is not None:
            output.append(indent + item_detail)
            continue
        semantic = translate_semantic_event_line(stripped, c)
        if semantic is not None:
            output.append(indent + semantic.strip())
            continue
        deterministic = deterministic_translate(stripped)
        if deterministic is not None:
            output.append(indent + deterministic)
            continue
        translated = cache_get(stripped, c)
        if translated is None:
            try:
                translated = translate_piece(stripped, c, force_robust=True)
                if numeric_values(stripped) and not numeric_items_preserved(stripped, translated):
                    raise RuntimeError("numeric_report_line_items_missing")
                cache_put(stripped, translated, c)
            except Exception as error:
                log("numeric report line fallback: %r source=%r" % (error, stripped[:160]), True)
                translated = line
        output.append(indent + translated)
    result = "\n".join(output)
    if not numeric_items_preserved(text, result):
        raise RuntimeError("NUMERIC_REPORT_FINAL_NUMERIC_ITEMS_MISSING")
    return result


def translate_xp_history_line(text, c):
    """Translate the semantic target while preserving XP and age fields exactly."""
    match = re.fullmatch(
        r"\s*([+-]?\d[\d,]*(?:\.\d+)?[kKmMbB]?)\s+xp from (.+?)\.\s+"
        r"(\d+) minutes? (\d+) seconds? ago\s*",
        str(text),
        re.I,
    )
    if not match:
        return None
    amount, target, minutes, seconds = match.groups()
    translated_target = cache_get(target, c)
    if translated_target is None:
        translated_target = translate_piece(target, c, force_robust=True)
        cache_put(target, translated_target, c)
    return "%s 經驗值，來自 %s；%s 分鐘 %s 秒前" % (
        amount, translated_target, minutes, seconds,
    )


RELATIVE_HISTORY_TIMESTAMP = re.compile(
    r"^(\s*)(.+?\S)\s+(\d+)\s+(seconds?|minutes?|hours?|days?)\s+ago(\s*)$",
    re.I,
)


def translate_relative_history_timestamp(text, c):
    """Cache a history message independently from its changing age suffix."""
    match = RELATIVE_HISTORY_TIMESTAMP.fullmatch(str(text))
    if not match:
        return None
    indent, message, amount, unit, trailing = match.groups()
    translated = translate_cached_phrase(message, c)
    translated = " ".join(str(translated).splitlines()).strip()
    if not translated:
        return None
    unit_zh = {
        "second": "秒", "seconds": "秒",
        "minute": "分鐘", "minutes": "分鐘",
        "hour": "小時", "hours": "小時",
        "day": "天", "days": "天",
    }[unit.lower()]
    return "%s%s %s %s前%s" % (indent, translated, amount, unit_zh, trailing)


def is_put_item_block(text):
    """Recognize a buffered run of fixed-shape container transfer messages."""
    lines = [line for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    return len(lines) >= 2 and all(PUT_ITEM_LINE.match(line) for line in lines)


def translate_cached_phrase(text, c):
    """Translate one complete semantic field; never split it into reusable words."""
    reviewed = reviewed_phrase_translation(text)
    if reviewed:
        return reviewed
    deterministic = deterministic_translate(text)
    if deterministic is not None:
        return deterministic
    field_config = dict(c)
    field_config["translation_cache_version"] = (
        int(c.get("translation_cache_version", 12)) * 1000 + STRUCTURED_FIELD_CACHE_VERSION
    )
    translated = cache_get(text, field_config)
    if translated is None:
        translated = translate_piece(text, c, force_robust=True)
        cache_put(text, translated, field_config)
    return " ".join(str(translated).splitlines()).strip()


def prefetch_cached_phrases(values, c):
    """Populate versioned field cache in bounded batches before reconstruction."""
    field_config = dict(c)
    field_config["translation_cache_version"] = (
        int(c.get("translation_cache_version", 12)) * 1000 + STRUCTURED_FIELD_CACHE_VERSION
    )
    missing = []
    seen = set()
    for value in values:
        value = str(value).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        if cache_get(value, field_config) is None:
            missing.append(value)
    for start in range(0, len(missing), 32):
        batch = missing[start:start + 32]
        translated = cloud_translate_many(batch)
        if translated is None:
            try:
                translated = translate_numbered_fields_once(batch, c) if len(batch) > 1 else [translate_piece(batch[0], c, force_robust=True)]
            except Exception as error:
                log("structured field batch fallback: %r" % error, True)
                translated = []
                for value in batch:
                    try:
                        translated.append(translate_piece(value, c, force_robust=True))
                    except Exception:
                        translated.append(value)
        for source, result in zip(batch, translated):
            ok, _reason = translation_sanity_ok(source, result)
            cache_put(source, result if ok else source, field_config)


def translate_safe_display_row(text, c):
    """Translate one visible row while preserving its numbers and row boundary."""
    source = str(text).strip()
    translated = translate_cached_phrase(source, c)
    if numeric_values(source) and not numeric_items_preserved(source, translated):
        log("structured display row numeric fallback: source=%r" % source[:160], True)
        return source
    return translated


def is_login_menu(text):
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    return bool(rows and rows[0] == "Welcome to Alter Aeon!" and
                sum(bool(re.match(r"^\d+\)\s+", line)) for line in rows) >= 3)


def is_character_creation_welcome(text):
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    joined = " ".join(rows)
    return (joined.startswith("Welcome to Alter Aeon, a fantasy adventure game set in a world ") and
            "If you already have a character, enter the name now." in joined and
            "Would you like to create a new character?" in joined)


def translate_character_creation_welcome(text):
    fixed = {
        "Welcome to Alter Aeon, a fantasy adventure game set in a world":
            "歡迎來到 Alter Aeon，這是一款設定在奇幻世界中的冒險遊戲，",
        "of swords and sorcery, magic and dragons!":
            "充滿刀劍、巫術、魔法與巨龍！",
        "If you already have a character, enter the name now.":
            "如果你已經有角色，請立即輸入角色名稱。",
        "If you are new, you must create and name a new character.":
            "如果你是新玩家，必須建立一個新角色並為其命名。",
        "Would you like to create a new character?":
            "你想建立新角色嗎？",
    }
    output = []
    for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        value = line.strip()
        output.append(fixed.get(value, value) if value else "")
    return "\n".join(output)


def translate_login_menu(text, c):
    fixed = {
        "Welcome to Alter Aeon!": "歡迎來到 Alter Aeon！",
        "Enter Selection ->": "請輸入選項 ->",
    }
    output = []
    for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        value = line.strip()
        numbered = re.match(r"^(\d+\)\s+)(.*)$", value)
        if value in fixed:
            output.append(fixed[value])
        elif numbered:
            output.append(numbered.group(1) + translate_safe_display_row(numbered.group(2), c))
        elif value:
            output.append(translate_safe_display_row(value, c))
        else:
            output.append("")
    return "\n".join(output)


def is_help_search_listing(text):
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    return bool(rows and rows[0] == "There is help available on the following topics:" and
                any(re.match(r"^\[\s*\d+\]\s+", line) for line in rows[1:]))


def translate_help_search_listing(text, c):
    output = []
    for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        value = line.strip()
        row = re.match(r"^(\[\s*\d+\]\s+)(.*)$", value)
        if value == "There is help available on the following topics:":
            output.append("以下主題有說明文件：")
        elif value == "To pick a particular help page, add in the number of the page.":
            output.append("若要選擇特定說明頁，請加上該頁的編號。")
        elif row:
            output.append(row.group(1) + translate_safe_display_row(row.group(2), c))
        elif value:
            output.append(translate_safe_display_row(value, c))
        else:
            output.append("")
    return "\n".join(output)


def is_friends_listing(text):
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    return len(rows) >= 2 and rows[0] in {"Logged in friends:", "Logged off friends:"}


def translate_friends_listing(text, c):
    headers = {"Logged in friends:": "已登入的好友：", "Logged off friends:": "已登出的好友："}
    output = []
    for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        value = line.strip()
        if value in headers:
            output.append(headers[value]); continue
        friend = re.match(r"^([A-Za-z][A-Za-z0-9_'’-]*)(?:\s+(\(.*\)))?$", value)
        if friend:
            name, detail = friend.groups()
            if not detail:
                output.append(name)
            elif detail.lower() == "(idle for a very long time)":
                output.append(name + "（已閒置很長時間）")
            else:
                output.append(name + " " + translate_safe_display_row(detail, c))
        elif value:
            output.append(translate_safe_display_row(value, c))
        else:
            output.append("")
    return "\n".join(output)


def is_skill_help_detail(text):
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    head = rows[:6]
    return bool(len(rows) >= 3 and
                any(line.startswith("Keywords are:") for line in head) and
                any(re.match(r"^(?:Skill|Spell):\s+", line, re.I) for line in head))


def parse_help_semantic_units(text):
    """Turn display-wrapped help into ordered, independently verifiable units."""
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    units, body = [], []
    in_usage = False
    metadata = re.compile(
        r"^(Showing page \d+\.|Keywords are:|Skill:|Spell:|"
        r"\((?:critical|important|helpful|useful)\)|Group:|Speed:|Usage:|"
        r"You can use .* while:)", re.I
    )

    def flush_body():
        if body:
            units.extend(("translate", chunk) for chunk in semantic_display_chunks("\n".join(body)))
            body[:] = []

    for row in rows:
        if metadata.match(row):
            flush_body()
            units.append(("fixed", "用法：") if row == "Usage:" else ("translate", row))
            in_usage = row == "Usage:"
            continue
        if in_usage and re.fullmatch(
            r"(?:[a-z][a-z-]*|[a-z][a-z-]*(?:\s+<[^>]+>)+)", row, re.I
        ):
            units.append(("raw", row))
            continue
        in_usage = False
        body.append(row)
    flush_body()
    return units


def translate_semantic_units(units, c, context="semantic"):
    """Translate ordered units without asking a model to reproduce structure."""
    prepared = {}
    missing = []
    for kind, source in units:
        if kind != "translate" or source in prepared or source in missing:
            continue
        translated = cache_get(source, c)
        if translated is not None and not any("\u3400" <= ch <= "\u9fff" for ch in translated):
            translated = None
        if translated is None:
            missing.append(source)
        else:
            prepared[source] = translated
    if missing:
        cloud_results = cloud_translate_many(missing)
        if cloud_results is not None:
            for source, translated in zip(missing, cloud_results):
                prepared[source] = translated
                cache_put(source, translated, c)

    output = []
    for kind, source in units:
        if kind in {"fixed", "raw"}:
            output.append(source)
            continue
        translated = prepared.get(source)
        # Old per-sentence cache rows can contain a model echo in English.  A
        # semantic prose unit is not complete unless it actually contains CJK.
        if translated is not None and not any("\u3400" <= ch <= "\u9fff" for ch in translated):
            translated = None
        try:
            if translated is None:
                translated = translate_piece(
                    source, c, force_robust=len(source) >= 180, allow_cloud=False
                )
            if not any("\u3400" <= ch <= "\u9fff" for ch in translated):
                raise RuntimeError(context.upper() + "_UNIT_UNTRANSLATED")
            if numeric_values(source) and not numeric_items_preserved(source, translated):
                raise RuntimeError(context.upper() + "_UNIT_NUMERIC_ITEMS_MISSING")
            translated = " ".join(translated.splitlines()).strip()
            cache_put(source, translated, c)
            prepared[source] = translated
        except Exception as error:
            log("%s unit fallback: %r source=%r" % (context, error, source[:160]), True)
            translated = source
        output.append(translated)
    if len(output) != len(units) or any(not value.strip() for value in output):
        raise RuntimeError(context.upper() + "_UNIT_RECONSTRUCTION_FAILED")
    return "\n".join(output)


def translate_skill_help_detail(text, c):
    """Translate field/command/prose units and reconstruct their exact order."""
    units = parse_help_semantic_units(text)
    if len(units) < 3:
        raise RuntimeError("HELP_SEMANTIC_UNITS_EMPTY")
    return translate_semantic_units(units, c, "help")


WRAPPED_DIALOGUE_START = re.compile(
    r"\b(?:says|asks|exclaims|shouts|whispers),\s*['\"]"
    r"|\btells\s+.+?,\s*['\"]",
    re.I,
)


def parse_wrapped_dialogue_units(text):
    """Group display-wrapped speech while keeping surrounding actions apart."""
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    start = next((index for index, row in enumerate(rows) if WRAPPED_DIALOGUE_START.search(row)), None)
    if start is None:
        return []
    end = None
    for index in range(start, len(rows)):
        if re.search(r"['\"]\s*$", rows[index]):
            end = index
            break
    if end is None:
        return []
    units = []
    if start:
        units.extend(("translate", chunk) for chunk in semantic_display_chunks("\n".join(rows[:start])))
    units.append(("translate", " ".join(rows[start:end + 1])))
    if end + 1 < len(rows):
        units.extend(("translate", chunk) for chunk in semantic_display_chunks("\n".join(rows[end + 1:])))
    return units if len(units) >= 2 else []


def is_wrapped_dialogue_block(text):
    return bool(parse_wrapped_dialogue_units(text))


def translate_wrapped_dialogue_block(text, c):
    return translate_semantic_units(parse_wrapped_dialogue_units(text), c, "wrapped_dialogue")


ROOM_PREVIEW_HEADERS = {
    "In the next room you see:": "在下一個房間，你可以看到：",
    "Nearby you see:": "在附近你可以看到：",
}
QUEST_INFORMATION_HEADER = re.compile(r"^Information for quest\s+(\d+):\s*$", re.I)
QUEST_INFORMATION_FOOTER = re.compile(
    r"^\(For more information, try 'quest extra\s+(\d+)'\.\)\s*$", re.I
)
AVAILABLE_LEVEL_SKILLS_HEADER = re.compile(r"^Available spells and skills at level\s+(\d+)\s*$", re.I)
AVAILABLE_LEVEL_SKILL_ROW = re.compile(
    r"^(General|Mage|Cleric|Thief|Warrior|Necromancer|Druid)\s+-\s+(.+?)\s+-\((guild|helpful|important|obscure|critical)\)\s*$",
    re.I,
)


def is_room_preview_block(text):
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    return len(rows) >= 2 and any(row in ROOM_PREVIEW_HEADERS for row in rows)


def parse_room_preview_units(text):
    """Preserve a looked-ahead room's title, prose and repeated entities."""
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    header_index = next((index for index, row in enumerate(rows) if row in ROOM_PREVIEW_HEADERS), None)
    if header_index is None:
        return []
    units = []
    if header_index:
        units.extend(("translate", chunk) for chunk in semantic_display_chunks("\n".join(rows[:header_index])))
    units.append(("fixed", ROOM_PREVIEW_HEADERS[rows[header_index]]))
    payload = rows[header_index + 1:]
    if not payload:
        return units
    if len(payload[0]) <= 100 and not re.search(r"[.!?。！？]$", payload[0]):
        units.append(("translate", payload.pop(0)))
    if not payload:
        return units
    trailing = trailing_independent_row_start("\n".join(payload))
    prose_rows = payload if trailing is None else payload[:trailing]
    entity_rows = [] if trailing is None else payload[trailing:]
    units.extend(("translate", chunk) for chunk in semantic_display_chunks("\n".join(prose_rows)))
    # Repeated NPCs/objects use one cached translation but retain every row.
    units.extend(("translate", row) for row in entity_rows)
    return units


def translate_room_preview_block(text, c):
    units = parse_room_preview_units(text)
    if len(units) < 2:
        raise RuntimeError("ROOM_PREVIEW_SEMANTIC_UNITS_EMPTY")
    return translate_semantic_units(units, c, "room_preview")


def is_available_level_skills_block(text):
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    return bool(len(rows) >= 2 and AVAILABLE_LEVEL_SKILLS_HEADER.fullmatch(rows[0])
                and all(AVAILABLE_LEVEL_SKILL_ROW.fullmatch(row) for row in rows[1:]))


def translate_available_level_skills_block(text, c):
    """Render one class/skill/importance row per source row."""
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    header = AVAILABLE_LEVEL_SKILLS_HEADER.fullmatch(rows[0])
    if not header:
        raise RuntimeError("AVAILABLE_LEVEL_SKILLS_HEADER_MISSING")
    class_names = {
        "general": "通用", "mage": "法師", "cleric": "牧師", "thief": "盜賊",
        "warrior": "戰士", "necromancer": "死靈法師", "druid": "德魯伊",
    }
    importance_names = {
        "guild": "公會", "helpful": "有幫助", "important": "重要",
        "obscure": "冷門", "critical": "關鍵",
    }
    glossary = load_skill_glossary()
    output = ["第 %s 級可用的法術與技能：" % header.group(1)]
    for row in rows[1:]:
        match = AVAILABLE_LEVEL_SKILL_ROW.fullmatch(row)
        if not match:
            raise RuntimeError("AVAILABLE_LEVEL_SKILLS_ROW_INVALID")
        class_name, skill_name, importance = match.groups()
        key = skill_name.strip().lower()
        translated_skill = glossary.get(key) or learned_skill_get(key)
        if not translated_skill:
            translated_skill = translate_unknown_skill(skill_name.strip(), c)
        output.append("%s - %s（%s）" % (
            class_names[class_name.lower()], translated_skill, importance_names[importance.lower()],
        ))
    if len(output) != len(rows):
        raise RuntimeError("AVAILABLE_LEVEL_SKILLS_LINE_COUNT_MISMATCH")
    return "\n".join(output)


def is_quest_information_block(text):
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    return bool(len(rows) >= 2 and QUEST_INFORMATION_HEADER.match(rows[0]))


def parse_quest_information_units(text):
    """Separate quest number, narrative sentences and the exact quest command."""
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    header = QUEST_INFORMATION_HEADER.match(rows[0]) if rows else None
    if not header:
        return []
    units = [("fixed", "任務 %s 的資訊：" % header.group(1))]
    body = []
    for row in rows[1:]:
        footer = QUEST_INFORMATION_FOOTER.match(row)
        if footer:
            if body:
                units.extend(("translate", chunk) for chunk in semantic_display_chunks("\n".join(body)))
                body[:] = []
            number = footer.group(1)
            units.append(("fixed", "（如需更多資訊，請輸入 'quest extra %s'。）" % number))
        else:
            body.append(row)
    if body:
        units.extend(("translate", chunk) for chunk in semantic_display_chunks("\n".join(body)))
    return units


def translate_quest_information_block(text, c):
    units = parse_quest_information_units(text)
    if len(units) < 2:
        raise RuntimeError("QUEST_INFORMATION_SEMANTIC_UNITS_EMPTY")
    return translate_semantic_units(units, c, "quest_information")


def is_equipment_advice(text):
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    return bool(rows and re.match(r"^Things .+ should consider getting\.\.\.$", rows[0], re.I) and
                any(line.startswith("FYI:") for line in rows[1:]))


def translate_equipment_advice(text, c):
    return "\n".join(
        translate_safe_display_row(line.strip(), c) if line.strip() else ""
        for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    )


def is_room_with_doors(text):
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    return len(rows) >= 3 and any(re.match(r"^Doors?\s+", line, re.I) for line in rows)


def translate_room_with_doors(text, c):
    """Preserve room titles, semantic sentences, visible entities and doors."""
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    output, body = [], []
    # At most two leading punctuation-free rows are area/room titles.
    while rows and len(output) < 2 and len(rows[0]) <= 90 and not re.search(r"[.!?]$", rows[0]):
        output.append(translate_safe_display_row(rows.pop(0), c))
    doors = []
    while rows and re.match(r"^Doors?\s+", rows[-1], re.I):
        doors.insert(0, rows.pop())
    body.extend(rows)
    output.extend(translate_safe_display_row(chunk, c) for chunk in semantic_display_chunks("\n".join(body)))
    direction_words = {"north": "北", "south": "南", "east": "東", "west": "西",
                       "northeast": "東北", "northwest": "西北", "southeast": "東南",
                       "southwest": "西南", "up": "上", "down": "下", "none": "無"}
    for door in doors:
        parts = door.split()[1:]
        output.append("門：" + "、".join(direction_words.get(part.lower().strip(","), part) for part in parts))
    return "\n".join(output)


def is_tip_block(text):
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    return len(rows) >= 2 and rows[0] in {"Tip:", "Tip!"}


def has_embedded_tip_block(text):
    rows = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return any(row.strip() in {"Tip:", "Tip!"} for row in rows[1:])


def translate_embedded_tip_block(text, c):
    """Preserve events before Tip:, then translate its wrapped prose whole."""
    rows = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    tip_index = next(
        index for index, row in enumerate(rows)
        if index and row.strip() in {"Tip:", "Tip!"}
    )
    prefix = "\n".join(rows[:tip_index]).strip()
    tip = "\n".join(rows[tip_index:]).strip()
    output = []
    if prefix:
        output.append(translate(prefix, c))
    output.append(translate_tip_block(tip, c))
    return "\n".join(output)


def translate_tip_block(text, c):
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    output = ["提示："]
    output.extend(translate_safe_display_row(chunk, c) for chunk in semantic_display_chunks("\n".join(rows[1:])))
    return "\n".join(output)


def is_syntax_help_block(text):
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    return len(rows) >= 2 and rows[0].startswith("Syntax:")


def translate_syntax_help_block(text, c):
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    output, body = [], []
    for row in rows:
        if row.startswith("Syntax:"):
            if body:
                output.extend(translate_safe_display_row(chunk, c) for chunk in semantic_display_chunks("\n".join(body)))
                body = []
            # Commands and argument punctuation must remain exact.
            output.append("語法：" + row[len("Syntax:"):].strip())
        else:
            body.append(row)
    if body:
        output.extend(translate_safe_display_row(chunk, c) for chunk in semantic_display_chunks("\n".join(body)))
    return "\n".join(output)


def is_book_text_block(text):
    first = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n", 1)[0].strip()
    return bool(re.match(r"^\d+\s+-\s+a book entitled,.*\bTopic:\s*", first, re.I))


def translate_book_text_block(text, c):
    rows = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    if not rows:
        return ""
    output = [translate_safe_display_row(rows[0], c)]
    paragraphs = semantic_display_chunks("\n".join(rows[1:]))
    # Keep requests bounded while avoiding one model call per display-wrapped row.
    for chunk in split_source("\n".join(paragraphs), 650):
        output.append(translate_safe_display_row(" ".join(chunk.splitlines()), c))
    return "\n".join(output)


def is_scan_listing(text):
    """Recognize Alter Aeon's directional scan table by shape, never names."""
    lines = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    if len(lines) < 2 or not SCAN_HEADER.fullmatch(lines[0]):
        return False
    return all(SCAN_ENTITY_ROW.fullmatch(line) or SCAN_PAREN_ROW.fullmatch(line) for line in lines[1:])


MOBS_IN_ROOM_HEADER = "Mobs in the room with you:"


def is_mobs_in_room_listing(text):
    """Recognize the room mob list even when the quiet buffer adds an event."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    substantive = [line.strip() for line in lines if line.strip()]
    return len(substantive) >= 2 and substantive[0] == MOBS_IN_ROOM_HEADER


def has_historical_fallback_shape(text):
    """Bypass legacy cache rows for formats now rendered deterministically."""
    patterns = (
        r"You know the following skills:\s+You don't know of any skills by that name\.",
        r"<\s*\d+hp\s+\d+m\s+\d+mv\s*>",
        r"You have \d+ practices? remaining\.",
        r"\d{1,2}\s+(?:am|pm)",
        r"freak\s+\d+!",
        r"You are level \d+ [A-Za-z]+\.",
        r"Your skill level is .+\.",
        r"--- Received \d+ lines, sent \d+ lines\.",
        r"--- Output buffer has \d+/\d+ lines in it \([\d.]+% full\)\.",
        r"--- Matched \d+ triggers, \d+ aliases, and \d+ timers fired\.",
    )
    lines = [line.strip() for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    return any(re.fullmatch(pattern, line, re.I) for line in lines for pattern in patterns)


def should_bypass_whole_block_cache(text):
    """Structured sources must not be trapped behind legacy whole-block rows."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return (is_room_prose_candidate(text) or
            any(deterministic_translate(line.strip()) is not None for line in lines if line.strip()) or
            any(reviewed_phrase_translation(line.strip()) is not None for line in lines if line.strip()) or
            any(semantic_event_match(line) for line in lines) or
            is_scan_listing(text) or is_class_skill_table(text) or is_practice_table(text) or
            is_mobs_in_room_listing(text) or has_historical_fallback_shape(text) or
            is_character_creation_welcome(text) or is_login_menu(text) or is_help_search_listing(text) or
            is_friends_listing(text) or is_skill_help_detail(text) or
            is_equipment_advice(text) or is_room_with_doors(text) or has_embedded_tip_block(text) or
            is_tip_block(text) or is_syntax_help_block(text) or is_book_text_block(text) or
            is_numeric_report_block(text) or
            is_wrapped_dialogue_block(text) or
            is_room_preview_block(text) or is_available_level_skills_block(text) or
            is_quest_information_block(text))


def translate_mobs_in_room_listing(text, c):
    """Keep every mob and adjacent room event on its original output row."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            output.append("")
        elif stripped == MOBS_IN_ROOM_HEADER:
            output.append("與你同處房間的生物：")
        else:
            # A quiet-period buffer may append an arrival/departure event.
            # One complete source row per request keeps that event separate.
            output.append(translate_cached_phrase(stripped, c))
    result = "\n".join(output)
    if len(result.split("\n")) != len(lines):
        raise RuntimeError("MOBS_IN_ROOM_LINE_COUNT_MISMATCH")
    return result


def is_probable_scan_name(value):
    """Preserve compact title-cased proper names such as Adin or Sir Kay."""
    value = str(value).strip()
    if not value or re.match(r"^(?:a|an|the)\b", value, re.I):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'’-]*", value)
    return bool(words) and len(words) <= 4 and all(word[0].isupper() for word in words)


def translate_scan_target(value, c):
    value = str(value).strip()
    if is_probable_scan_name(value):
        return value
    return translate_cached_phrase(value, c)


def translate_scan_parenthesized(description, c):
    """Render door state fields deterministically; translate only unknown text."""
    match = re.fullmatch(r"(?:A|An|The)\s+(.+?)\s+door\s+is\s+(closed|open|locked)\.", description, re.I)
    if not match:
        return translate_cached_phrase(description, c)
    material, state = match.groups()
    material_key = material.strip().lower()
    material_zh = SCAN_DOOR_MATERIALS.get(material_key)
    if material_zh is None:
        material_zh = translate_cached_phrase(material.strip(), c)
    return "一扇%s門%s。" % (material_zh, SCAN_DOOR_STATES[state.lower()])


def translate_scan_listing(text, c):
    """Translate scan rows without exposing directions or distances to the LLM."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            output.append("")
            continue
        if SCAN_HEADER.fullmatch(stripped):
            output.append("你掃描周圍區域……")
            continue
        entity = SCAN_ENTITY_ROW.fullmatch(stripped)
        if entity:
            direction, distance, target = entity.groups()
            output.append("%s　距離 %s：%s" % (
                SCAN_DIRECTIONS[direction.lower()], distance, translate_scan_target(target, c),
            ))
            continue
        parenthesized = SCAN_PAREN_ROW.fullmatch(stripped)
        if parenthesized:
            direction, description = parenthesized.groups()
            output.append("（%s）%s" % (
                SCAN_DIRECTIONS[direction.lower()], translate_scan_parenthesized(description, c),
            ))
            continue
        raise RuntimeError("SCAN_ROW_PARSE_FAILED: " + stripped[:120])
    result = "\n".join(output)
    if len(result.split("\n")) != len(lines):
        raise RuntimeError("SCAN_FINAL_LINE_COUNT_MISMATCH")
    if not numeric_items_preserved(text, result):
        raise RuntimeError("SCAN_FINAL_NUMERIC_ITEMS_MISSING")
    return result


def action_template_match(line):
    """Return a strict action template; ambiguous plain 'You get ...' is excluded."""
    for kind, pattern in (
        ("buy_from", BUY_ITEM_LINE),
        ("put_in", PUT_ITEM_LINE),
        ("get_from", GET_FROM_LINE),
        ("give_to", GIVE_ITEM_LINE),
    ):
        match = pattern.fullmatch(str(line))
        if match:
            # "You get 2 items from <container>: item, item" is a different
            # table-like grammar.  Treating "2 items" as the item name and the
            # entire remainder as a container would corrupt both field caches.
            if kind == "get_from" and re.fullmatch(r"\d+ items?", match.group(2), re.I):
                continue
            return kind, match
    return None


def semantic_event_match(line):
    """Recognize reviewed visible event shells taken from Mush-Z triggers."""
    source = str(line)
    for kind, pattern in SEMANTIC_EVENT_PATTERNS:
        match = pattern.fullmatch(source)
        if not match:
            continue
        if kind == "get_item" and re.match(r"\d+ items?:", match.group(2), re.I):
            # Mush-Z reconstructs this aggregate into a table-like row.
            continue
        return kind, match
    return None


def translate_semantic_event_line(line, c):
    """Translate a stable shell and cache only its changing semantic fields."""
    matched = semantic_event_match(line)
    if not matched:
        return None
    kind, match = matched
    groups = match.groups()
    if kind == "blade_spin":
        indent, weapon, trailing = groups
        return "%s你開始揮動並旋轉刀刃「%s」……%s" % (indent, weapon, trailing)
    if kind in {"blade_flick_hit", "blade_flick_miss"}:
        indent, weapon, target, trailing = groups
        template = "你將刀刃「%s」迅速揮向%s，成功擊中！" if kind == "blade_flick_hit" else "你將刀刃「%s」迅速揮向%s，但對方避開了攻擊。"
        return "%s%s%s" % (indent, template % (weapon, translate_cached_phrase(target, c)), trailing)
    if kind == "blade_reaction":
        indent, target, reaction, weapon, trailing = groups
        reaction_zh = "看起來有些惱火" if reaction.lower().startswith("looks") else "發出奇怪的聲音"
        return "%s當你將刀刃「%s」刺入%s背部時，對方%s。%s" % (
            indent, weapon, translate_cached_phrase(target, c), reaction_zh, trailing,
        )
    if kind == "damage_other":
        indent, attacker, damage_type, grade, target, punctuation, trailing = groups
        grade_key = re.sub(r"[^A-Z]", "", grade.upper())
        grade_zh = {
            "HEALS": "治癒", "ANNOYS": "騷擾", "SCRATCHES": "擦傷", "HITS": "擊中",
            "INJURES": "傷害", "WOUNDS": "創傷", "MAULS": "重創", "DECIMATES": "嚴重打擊",
            "DEVASTATES": "毀滅性重創", "MAIMS": "致殘", "MUTILATES": "殘害",
            "DISMEMBERS": "肢解", "DISEMBOWELS": "開膛", "MASSACRES": "屠殺",
            "OBLITERATES": "徹底摧毀", "DEMOLISHES": "粉碎", "DESTROYS": "摧毀",
            "ANNIHILATES": "殲滅",
        }[grade_key]
        return "%s%s的%s對%s造成%s%s%s" % (
            indent, translate_cached_phrase(attacker, c), translate_cached_phrase(damage_type, c),
            translate_cached_phrase(target, c), grade_zh, punctuation, trailing,
        )
    if kind == "aura_fades":
        indent, color, actor, trailing = groups
        color_zh = "白色" if color.lower() == "white" else "黑色"
        return "%s%s身旁的%s光環消退了。%s" % (indent, translate_cached_phrase(actor, c), color_zh, trailing)
    if kind == "actor_white_aura":
        indent, actor, trailing = groups
        return "%s%s被白色光環包圍。%s" % (indent, translate_cached_phrase(actor, c), trailing)
    if kind == "restored_health":
        indent, actor, trailing = groups
        return "%s%s使你完全恢復健康！%s" % (indent, translate_cached_phrase(actor, c), trailing)
    if kind in {"get_gold", "drop_gold"}:
        indent, amount, trailing = groups
        template = "你取得 %s 枚金幣。" if kind == "get_gold" else "你丟下 %s 枚金幣。"
        return "%s%s%s" % (indent, template % amount, trailing)
    if kind == "get_gold_from":
        indent, amount, source, trailing = groups
        return "%s你從%s取得 %s 枚金幣。%s" % (indent, translate_cached_phrase(source, c), amount, trailing)
    if kind == "gives_you":
        indent, actor, item, trailing = groups
        return "%s%s將%s交給你。%s" % (indent, translate_cached_phrase(actor, c), translate_cached_phrase(item, c), trailing)
    if kind == "item_compare":
        indent, first, relation, second, trailing = groups
        relation_zh = {"worse": "比%s差", "a bit better": "比%s稍好", "looks better": "看起來比%s好"}[relation.lower()]
        return "%s%s%s。%s" % (
            indent, translate_cached_phrase(first, c), relation_zh % translate_cached_phrase(second, c), trailing,
        )
    if kind in {"starts_following_you", "stops_following_you"}:
        indent, actor, trailing = groups
        template = "%s開始跟隨你。" if kind == "starts_following_you" else "%s停止跟隨你。"
        return "%s%s%s" % (indent, template % translate_cached_phrase(actor, c), trailing)
    if kind == "you_follow":
        indent, action, actor, trailing = groups
        template = "你開始跟隨%s。" if action.lower() == "start" else "你停止跟隨%s。"
        return "%s%s%s" % (indent, template % translate_cached_phrase(actor, c), trailing)
    if kind in {"group_add", "group_member", "group_left", "stops_resting"}:
        indent, actor, trailing = groups
        template = {
            "group_add": "你將%s加入隊伍。",
            "group_member": "%s加入了隊伍。",
            "group_left": "%s離開了隊伍。",
            "stops_resting": "%s停止休息並站了起來。",
        }[kind]
        return "%s%s%s" % (indent, template % translate_cached_phrase(actor, c), trailing)
    if kind in {"teleport_vanish", "teleport_appear"}:
        indent, actor, trailing = groups
        template = "%s消失在閃爍的紅光中。" if kind == "teleport_vanish" else "%s在房間中央的閃爍藍光中現身。"
        return "%s%s%s" % (indent, template % translate_cached_phrase(actor, c), trailing)
    if kind == "unique_item":
        indent, item, trailing = groups
        return "%s%s（唯一）%s" % (indent, translate_cached_phrase(item, c), trailing)
    if kind == "actor_puts":
        indent, actor, item, container, trailing = groups
        return "%s%s將%s放入%s。%s" % (
            indent, translate_cached_phrase(actor, c),
            translate_cached_phrase(item, c),
            translate_cached_phrase(container, c), trailing,
        )
    if kind == "equipment":
        indent, action, item, trailing = groups
        templates = {
            "wearing": "你正穿戴著%s。", "holding": "你正拿著%s。",
            "wielding": "你正裝備著%s。", "carrying": "你正攜帶著%s。",
        }
        return "%s%s%s" % (
            indent, templates[action.lower()] % translate_cached_phrase(item, c), trailing,
        )
    if kind == "sniffs_air":
        indent, actor, trailing = groups
        return "%s%s嗅了嗅空氣，像是聞到附近的氣味。%s" % (
            indent, translate_cached_phrase(actor, c), trailing,
        )
    if kind == "actor_dead":
        indent, actor, trailing = groups
        return "%s%s死了！%s" % (indent, translate_cached_phrase(actor, c), trailing)
    if kind == "actor_arrived":
        indent, actor, trailing = groups
        return "%s%s來了。%s" % (indent, translate_cached_phrase(actor, c), trailing)
    if kind == "throw_shadow":
        indent, projectile, target, missed, trailing = groups
        template = "你向%s投出%s，但沒有命中！" if missed else "你向%s投出%s！"
        return "%s%s%s" % (
            indent,
            template % (translate_cached_phrase(target, c), translate_cached_phrase(projectile, c)),
            trailing,
        )
    if kind == "no_loot":
        indent, actor, trailing = groups
        return "%s%s的屍體已經沒有東西可搜刮了。%s" % (
            indent, translate_cached_phrase(actor, c), trailing,
        )
    if kind == "block_attack":
        indent, trailing = groups
        return "%s你擋住了對方的攻擊。%s" % (indent, trailing)
    if kind == "door_action":
        indent, action, target, trailing = groups
        templates = {"open": "你打開%s。", "close": "你關上%s。", "lock": "你鎖上%s。", "unlock": "你解鎖%s。"}
        return "%s%s%s" % (
            indent, templates[action.lower()] % translate_cached_phrase(target, c), trailing,
        )
    if kind == "door_closed":
        indent, target, trailing = groups
        return "%s%s關著。%s" % (indent, translate_cached_phrase(target, c), trailing)
    if kind == "sacrifice_gold":
        indent, amount, offered, trailing = groups
        return "%s你奉獻%s，獲得 %s 枚金幣。%s" % (
            indent, translate_cached_phrase(offered, c), amount, trailing,
        )
    if kind == "condition":
        indent, condition, trailing = groups
        translated = {
            "a few scratches": "你有幾處擦傷。",
            "some small wounds and bruises": "你有一些小傷口和瘀青。",
            "quite a few wounds": "你身上有不少傷口。",
            "big nasty wounds and scratches": "你有嚴重的傷口與擦傷。",
        }[condition.lower()]
        return "%s%s%s" % (indent, translated, trailing)
    if kind in {"physical_reserve", "sense_life"}:
        indent, trailing = groups
        translated = {
            "physical_reserve": "你體內深處的體力儲備已經恢復。",
            "sense_life": "你感覺到房間裡有隱藏的生命。",
        }[kind]
        return "%s%s%s" % (indent, translated, trailing)
    if kind == "pray_transport":
        indent, deity, trailing = groups
        return "%s你向%s祈求傳送……%s" % (
            indent, translate_cached_phrase(deity, c), trailing,
        )
    if kind == "directional_departure":
        indent, actor, action, direction, trailing = groups
        action_zh = {
            "leaves": "離開", "flies": "飛走", "walks": "走去",
            "runs": "跑去", "departs": "離去",
        }[action.lower()]
        direction_zh = {
            "north": "北方", "south": "南方", "east": "東方", "west": "西方",
            "northeast": "東北方", "northwest": "西北方",
            "southeast": "東南方", "southwest": "西南方", "up": "上方", "down": "下方",
        }[direction.lower()]
        return "%s%s往%s%s。%s" % (
            indent, translate_cached_phrase(actor, c), direction_zh, action_zh, trailing,
        )
    if kind in {"get_item", "drop_item", "stop_using"}:
        indent, item, trailing = groups
        item_zh = translate_cached_phrase(item, c)
        template = {
            "get_item": "你取得%s。",
            "drop_item": "你丟下%s。",
            "stop_using": "你停止使用%s。",
        }[kind]
        return "%s%s%s" % (indent, template % item_zh, trailing)
    if kind == "cast_spell":
        indent, actor, spell, trailing = groups
        return "%s%s施放「%s」。%s" % (
            indent, translate_cached_phrase(actor, c),
            translate_cached_phrase(spell, c), trailing,
        )
    if kind in {
        "actor_here", "actor_darkened", "mortally_wounded", "keeps_bleeding",
        "stops_bleeding", "anticipates_bloodletting", "trip_fly_recovery",
        "trip_avoided", "too_weak_to_attack", "collapses_branches", "sprays_webs",
    }:
        indent, actor, trailing = groups
        actor_zh = translate_cached_phrase(actor, c)
        template = {
            "actor_here": "%s在這裡。",
            "actor_darkened": "%s籠罩在黑暗中。",
            "mortally_wounded": "%s受到致命傷，若未獲救很快便會死亡。",
            "keeps_bleeding": "%s還在流血！",
            "stops_bleeding": "%s的流血停止了。",
            "anticipates_bloodletting": "%s預判了你的放血刺擊，避開了攻擊。",
            "trip_fly_recovery": "%s試圖絆倒你，但你的飛行法術幫助你恢復平衡。",
            "trip_avoided": "%s試圖絆倒你，但你早已看穿並避開。",
            "too_weak_to_attack": "%s虛弱得無法攻擊。",
            "collapses_branches": "%s倒在一堆斷枝中。",
            "sprays_webs": "%s朝你全身噴出蛛網！",
        }[kind]
        return "%s%s%s" % (indent, template % actor_zh, trailing)
    if kind in {"receive_xp", "limited_xp"}:
        indent, amount, trailing = groups
        template = "你獲得 %s 點經驗值。" if kind == "receive_xp" else "你從這場戰鬥中學到的不多，但仍獲得 %s 點經驗值。"
        return "%s%s%s" % (indent, template % amount, trailing)
    if kind == "gain_favor":
        indent, deity, trailing = groups
        return "%s你獲得%s的青睞！%s" % (
            indent, translate_cached_phrase(deity, c), trailing,
        )
    if kind == "achievement":
        indent, achievement, trailing = groups
        return "%s你完成了成就：%s%s" % (
            indent, translate_cached_phrase(achievement, c), trailing,
        )
    if kind == "sacrifice":
        indent, actor, offered, trailing = groups
        return "%s你將%s奉獻給%s。%s" % (
            indent, translate_cached_phrase(offered, c),
            translate_cached_phrase(actor, c), trailing,
        )
    if kind in {"miss", "dodge"}:
        indent, actor, target, trailing = groups
        actor_zh = translate_cached_phrase(actor, c)
        target_zh = translate_cached_phrase(target, c)
        template = "%s沒有擊中%s。" if kind == "miss" else "%s閃避了%s的攻擊。"
        return "%s%s%s" % (indent, template % (actor_zh, target_zh), trailing)
    if kind == "parry":
        indent, actor, target, trailing = groups
        return "%s%s招架了%s的攻擊。%s" % (
            indent, translate_cached_phrase(actor, c), translate_cached_phrase(target, c), trailing,
        )
    return None


def is_semantic_event_block(text):
    lines = [line for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    return bool(lines) and all(semantic_event_match(line) for line in lines)


def prefetch_semantic_event_fields(lines, c):
    """Batch variable fields from visible trigger-shaped event runs."""
    values = []
    for line in lines:
        matched = semantic_event_match(line)
        if not matched:
            continue
        kind, match = matched
        groups = match.groups()
        if kind == "actor_puts": values.extend(groups[1:4])
        elif kind in {"blade_flick_hit", "blade_flick_miss"}: values.append(groups[2])
        elif kind == "blade_reaction": values.append(groups[1])
        elif kind == "damage_other": values.extend((groups[1], groups[2], groups[4]))
        elif kind == "aura_fades": values.append(groups[2])
        elif kind in {"actor_white_aura", "restored_health", "starts_following_you", "stops_following_you", "group_add", "group_member", "group_left", "stops_resting", "teleport_vanish", "teleport_appear", "unique_item", "actor_here", "actor_darkened", "actor_dead", "actor_arrived", "mortally_wounded", "keeps_bleeding", "stops_bleeding", "anticipates_bloodletting", "trip_fly_recovery", "trip_avoided", "too_weak_to_attack", "collapses_branches", "sprays_webs"}: values.append(groups[1])
        elif kind == "parry": values.extend((groups[1], groups[2]))
        elif kind == "get_gold_from": values.append(groups[2])
        elif kind == "gives_you": values.extend(groups[1:3])
        elif kind == "item_compare": values.extend((groups[1], groups[3]))
        elif kind == "you_follow": values.append(groups[2])
    if values:
        prefetch_cached_phrases(values, c)


def translate_semantic_event_block(text, c):
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    prefetch_semantic_event_fields(lines, c)
    output = []
    for line in lines:
        if not line.strip():
            output.append("")
            continue
        try:
            rendered = translate_semantic_event_line(line, c)
            if rendered is None:
                raise RuntimeError("semantic_event_not_rendered")
            if numeric_values(line) and not numeric_items_preserved(line, rendered):
                raise RuntimeError("semantic_event_numeric_items_missing")
            output.append(rendered)
        except Exception as error:
            log("semantic-event line fallback: %r source=%r" % (error, line[:160]), True)
            output.append(line)
    result = "\n".join(output)
    if len(result.split("\n")) != len(lines):
        raise RuntimeError("SEMANTIC_EVENT_LINE_COUNT_MISMATCH")
    return result


def translate_action_line(line, c):
    """Reconstruct one unambiguous action from exact full-field cache entries."""
    matched = action_template_match(line)
    if not matched:
        return None
    kind, match = matched
    groups = match.groups()
    if kind == "put_in":
        indent, item, container, trailing = groups
        return "%s你將%s放入%s。%s" % (
            indent, translate_cached_phrase(item, c),
            translate_cached_phrase(container, c), trailing,
        )
    if kind == "get_from":
        indent, item, container, trailing = groups
        return "%s你從%s取得%s。%s" % (
            indent, translate_cached_phrase(container, c),
            translate_cached_phrase(item, c), trailing,
        )
    if kind == "give_to":
        indent, item, target, trailing = groups
        return "%s你將%s交給%s。%s" % (
            indent, translate_cached_phrase(item, c),
            translate_cached_phrase(target, c), trailing,
        )
    indent, item, target, price, trailing = groups
    return "%s你以 %s 枚金幣向%s購買%s。%s" % (
        indent, price, translate_cached_phrase(target, c),
        translate_cached_phrase(item, c), trailing,
    )


def is_action_template_block(text):
    lines = [line for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    return bool(lines) and all(action_template_match(line) for line in lines)


def translate_action_template_block(text, c):
    """Translate strict action rows independently; one novel field falls back one row."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output = []
    for line in lines:
        if not line.strip():
            output.append("")
            continue
        try:
            rendered = translate_action_line(line, c)
            if rendered is None:
                raise RuntimeError("action_template_not_rendered")
            if numeric_values(line) and not numeric_items_preserved(line, rendered):
                raise RuntimeError("action_template_numeric_items_missing")
            output.append(rendered)
        except Exception as error:
            log("action-template line fallback: %r source=%r" % (error, line[:160]), True)
            output.append(line)
    result = "\n".join(output)
    if len(result.split("\n")) != len(lines):
        raise RuntimeError("ACTION_TEMPLATE_LINE_COUNT_MISMATCH")
    if not numeric_items_preserved(text, result):
        raise RuntimeError("ACTION_TEMPLATE_NUMERIC_ITEMS_MISSING")
    return result


def combat_template_match(line):
    for kind, pattern in COMBAT_TARGET_PATTERNS:
        match = pattern.fullmatch(str(line))
        if match:
            return kind, match
    return None


def translate_combat_template_line(line, c):
    """Translate a combat shell while caching the complete NPC phrase once."""
    matched = combat_template_match(line)
    if not matched:
        return None
    kind, match = matched
    if kind == "blade_back":
        indent, weapon, target, trailing = match.groups()
        return "%s你將刀刃「%s」刺入%s背部，造成致命傷。%s" % (
            indent, weapon, translate_cached_phrase(target, c), trailing,
        )
    indent, target, trailing = match.groups()
    target_zh = translate_cached_phrase(target, c)
    templates = {
        "stomp_crunch": "你重踩%s，並聽見碎裂聲！",
        "stomp_toes": "你重踩%s的腳趾！",
        "lunge": "你猛撲向%s！",
        "evaluate": "你迅速評估%s的護甲與身體構造……",
        "stomp": "你重踩%s！",
        "weapon_display": "你將武器展示的最後一連串動作對準%s……",
        "quick_thrust": "你迅速將武器刺向%s！",
        "draw_thrust": "你收回武器，接著刺向%s！",
        "circle": "你繞到%s身後，找到絕佳機會！",
        "downward_thrust": "你朝%s使出強力下刺，試圖給予致命一擊！",
        "feign": "你對%s佯裝突然攻擊，對方移動格擋！",
        "death_cry": "你聽見%s的死亡哀號，頓時血液凝結！",
        "slit_throat": "你割開%s的喉嚨。",
        "dead": "%s已經死亡！",
        "backstab_damage": "你的背刺對%s造成了相當大的傷害！",
        "dirt": "你將泥土丟進%s的臉，使其失明！",
    }
    return "%s%s%s" % (indent, templates[kind] % target_zh, trailing)


def is_combat_template_block(text):
    lines = [line for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    return bool(lines) and all(combat_template_match(line) for line in lines)


def translate_combat_template_block(text, c):
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output = []
    for line in lines:
        if not line.strip():
            output.append("")
            continue
        try:
            rendered = translate_combat_template_line(line, c)
            if rendered is None:
                raise RuntimeError("combat_template_not_rendered")
            if numeric_values(line) and not numeric_items_preserved(line, rendered):
                raise RuntimeError("combat_template_numeric_items_missing")
            output.append(rendered)
        except Exception as error:
            log("combat-template line fallback: %r source=%r" % (error, line[:160]), True)
            output.append(line)
    result = "\n".join(output)
    if len(result.split("\n")) != len(lines):
        raise RuntimeError("COMBAT_TEMPLATE_LINE_COUNT_MISMATCH")
    return result


def translate_put_item_block(text, c):
    """Reuse inventory/container phrases; preserve every transfer row and its order."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output = []
    for line in lines:
        if not line.strip():
            output.append("")
            continue
        match = PUT_ITEM_LINE.match(line)
        if not match:
            output.append(line)
            continue
        indent, item, container, trailing = match.groups()
        try:
            item_zh = translate_cached_phrase(item, c)
            container_zh = translate_cached_phrase(container, c)
            output.append("%s你將%s放入%s。%s" % (indent, item_zh, container_zh, trailing))
        except Exception as error:
            log("put-item line fallback: %r source=%r" % (error, line[:160]), True)
            output.append(line)
    result = "\n".join(output)
    if len(result.split("\n")) != len(lines):
        raise RuntimeError("PUT_ITEM_LINE_COUNT_MISMATCH")
    if not numeric_items_preserved(text, result):
        raise RuntimeError("PUT_ITEM_NUMERIC_ITEMS_MISSING")
    return result


def is_quest_help_block(text):
    value = str(text).replace("\r\n", "\n").replace("\r", "\n")
    return value.startswith("Sorry, unknown option for 'quest' command.\nQuests Help\n")


def translate_quest_help_block(text):
    """Render the fixed command table locally while leaving unknown future rows visible."""
    output = []
    for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        fixed = QUEST_HELP_FIXED_LINES.get(line)
        if fixed is not None:
            output.append(fixed)
            continue
        command = re.match(r"^(\s*)(quest.*?)\s{2,}-\s(.+?)\s*$", line, re.I)
        if command:
            indent, syntax, description = command.groups()
            translated = QUEST_HELP_DESCRIPTIONS.get(description)
            output.append("%s%-24s - %s" % (indent, syntax, translated or description))
            continue
        output.append(line)
    return "\n".join(output)


def translate_repeated_line_block(text, c):
    """Translate legitimate duplicate object/event rows once, then reconstruct."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    counts = {}
    for line in lines:
        stripped = line.strip()
        counts[stripped] = counts.get(stripped, 0) + 1
    repeated = {
        line for line, count in counts.items()
        if count >= 2 and len(re.sub(r"\s+", "", line)) >= 12
    }
    output, normal_buffer, translated_repeats = [], [], {}

    def flush_normal():
        if normal_buffer:
            block = "\n".join(normal_buffer)
            if has_deterministic_lines(block):
                output.append(translate_mixed_deterministic_block(block, c))
            else:
                output.append(translate_piece(block, c, force_robust=len(block) >= 180))
            normal_buffer[:] = []

    for line in lines:
        stripped = line.strip()
        if stripped not in repeated:
            normal_buffer.append(line)
            continue
        flush_normal()
        if stripped not in translated_repeats:
            translated_repeats[stripped] = translate_piece(stripped, c, force_robust=True)
        output.append(translated_repeats[stripped])
    flush_normal()
    result = "\n".join(output)
    ok, reason = translation_sanity_ok(text, result)
    if not ok:
        raise RuntimeError("REPEATED_LINES_FINAL_SANITY_" + reason)
    return result


def translate_trailing_independent_rows(text, c):
    """Keep room NPC/object rows separate from the translated room prose."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    start = trailing_independent_row_start(text)
    if start is None:
        return translate_piece(text, c)
    prefix = "\n".join(lines[:start])
    prefix_translation = (
        translate_room_prose_cached(prefix, c)
        if is_room_prose_candidate(prefix)
        else translate_piece(prefix, c, force_robust=len(prefix) >= 180)
    )
    # An aligned room prefix deliberately contains one semantic row for the
    # title and each complete sentence.  Do not flatten those rows merely
    # because NPC/object rows follow the room description.
    output = [line.strip() for line in prefix_translation.splitlines() if line.strip()]
    for source_line in lines[start:]:
        stripped = source_line.strip()
        translated = cache_get(stripped, c)
        if translated is None:
            translated = translate_piece(stripped, c, force_robust=True)
            cache_put(stripped, translated, c)
        output.append(" ".join(translated.splitlines()).strip())
    result = "\n".join(output)
    ok, reason = translation_sanity_ok(text, result)
    if not ok:
        raise RuntimeError("TRAILING_ROWS_FINAL_SANITY_" + reason)
    return result


SKILL_RATINGS = {
    "very bad": "非常差", "bad": "差", "poor": "不佳", "fair": "尚可",
    "average": "普通", "moderate": "中等", "good": "良好",
    "very good": "很好", "exceptional": "卓越", "perfect": "完美",
}
SKILL_SECTIONS = {
    "Mage": "法師", "Thief": "盜賊", "Warrior": "戰士",
    "Druid": "德魯伊", "General": "通用",
}
SKILL_LINE = re.compile(
    r"^(\s*)(.*?)(?:\s{2,})(very bad|very good|exceptional|moderate|average|perfect|poor|fair|good|bad)\s+(\d+%)\s*$",
    re.IGNORECASE,
)
PRACTICE_HEADER = re.compile(r"^You have\s+(\d+|one)\s+practices?\s+left\.$", re.IGNORECASE)
PRACTICE_COLUMN_HEADER = re.compile(r"^-+\s+Int\s+Wis\s+Chr\s+Lvl\s+-+$", re.IGNORECASE)
PRACTICE_LINE = re.compile(
    r"^(\s*)(.*?)(\s{2,})"
    r"(not learned|very bad|very good|exceptional|moderate|average|perfect|poor|fair|good|bad)"
    r"(\s+)(\S.*)$",
    re.IGNORECASE,
)
PRACTICE_FIXED_PROSE = {
    "Mage elemental cold spellgroup": "法師元素冰系法術組",
    "Mage elemental fire spellgroup": "法師元素火系法術組",
    "Mage illusion spellgroup": "法師幻術組",
    "Mage basic magics": "法師基礎魔法",
    "Mage elemental lightning spellgroup": "法師元素閃電法術組",
    "Mage force fields": "法師力場",
    "Cleric divine aid spellgroup": "牧師神助法術組",
    "Cleric healing spellgroup": "牧師治療法術組",
    "Cleric divine conjuration spellgroup": "牧師神聖召喚法術組",
    "Cleric inquisition spellgroup": "牧師審判法術組",
    "Cleric tribulation spellgroup": "牧師苦難法術組",
    "Thief tinkering": "盜賊工藝",
    "Thief defensive fighting skills": "盜賊防禦戰鬥技巧",
    "Thief stealth skills": "盜賊潛行技能",
    "Thief stealing skill group": "盜賊偷竊技能組",
    "Thief poison skill group": "盜賊毒術組",
    "Thief ranged fighting skills": "盜賊遠程戰鬥技巧",
    "Thief melee fighting skills": "盜賊近戰技巧",
    "Thief shadow disciplines": "盜賊暗影訓練",
    "Warrior hand to hand combat": "戰士徒手格鬥",
    "Warrior group tactics": "戰士團隊戰術",
    "Warrior fighting styles": "戰士戰鬥風格",
    "Warrior weapon handling": "戰士武器操作",
    "Warrior iron body": "戰士鐵身",
    "Barbarian blood skills": "野蠻人血之技能",
    "Warcries": "戰吼",
    "Warrior power attacks": "戰士力量攻擊",
    "Druid plant lore": "德魯伊植物知識",
    "Rangers Guild Trade Skills": "遊俠公會貿易技能",
    "Culinary skills": "烹飪技能",
    "Decantation": "分裝術",
    "Orienteering": "定向越野",
    "Lapidarists Guild Trade Skills": "寶石工匠公會貿易技能",
    "Ranged weapon skills": "遠程武器技能",
    "Woodwrights Guild Trade Skills": "木匠公會貿易技能",
    "Smiths Guild Trade Skills": "鐵匠公會貿易技能",
    "General skills": "一般技能",
    "While you can learn critical spells and skills on your own, you need":
        "雖然你可以自行學會關鍵法術與技能，但仍需要",
    "to find a teacher or guildmaster to learn less common abilities.":
        "尋找老師或公會會長，才能學習較少見的能力。",
}
CLASS_SKILL_HEADER = re.compile(
    r"^(Spell|Skill)\s+Mage\s+Cler\s+Thie\s+Warr\s+Necr\s+Drui\s+Lvl\s+Prac\s+Known\s+Dependencies\s*$",
    re.IGNORECASE,
)
CLASS_SKILL_DEPENDENCY = re.compile(r"^(.*?)\s*\((important|helpful)\)\s*$", re.IGNORECASE)


def load_skill_glossary():
    global SKILL_GLOSSARY
    if SKILL_GLOSSARY is not None:
        return SKILL_GLOSSARY
    try:
        raw = json.loads(SKILL_GLOSSARY_FILE.read_text(encoding="utf-8"))
        SKILL_GLOSSARY = {str(k).strip().lower(): str(v).strip() for k, v in raw.items() if str(v).strip()}
    except Exception as e:
        log("skill glossary load failed: %r" % e, True)
        SKILL_GLOSSARY = {}
    return SKILL_GLOSSARY


def learned_skill_get(name):
    db = cache_connection()
    if db is None:
        return None
    try:
        db.execute("CREATE TABLE IF NOT EXISTS skill_glossary(source_name TEXT PRIMARY KEY, translated_name TEXT NOT NULL, updated_at INTEGER NOT NULL)")
        row = db.execute("SELECT translated_name FROM skill_glossary WHERE source_name=?", (name.lower(),)).fetchone()
        return row[0] if row else None
    except Exception as e:
        log("skill glossary read failed: %r" % e, True)
        return None


def learned_skill_put(name, translated):
    db = cache_connection()
    if db is None:
        return
    try:
        db.execute("CREATE TABLE IF NOT EXISTS skill_glossary(source_name TEXT PRIMARY KEY, translated_name TEXT NOT NULL, updated_at INTEGER NOT NULL)")
        db.execute("INSERT OR REPLACE INTO skill_glossary(source_name,translated_name,updated_at) VALUES(?,?,?)",
                   (name.lower(), translated, int(time.time())))
        db.commit()
    except Exception as e:
        log("skill glossary write failed: %r" % e, True)


def translate_unknown_skill(name, c):
    timeout = max(3, float(c.get("request_timeout_seconds", 25)))
    prompt = ("Translate this English RPG skill name into Traditional Chinese. "
              "Output only the translated skill name.\nEnglish: " + name + "\nTraditional Chinese:")
    response = http_post("/completion", {
        "prompt": prompt, "n_predict": 48, "temperature": 0.0,
        "repeat_penalty": 1.1, "repeat_last_n": 64, "stream": False,
    }, timeout)
    translated = to_traditional_characters((response.get("content") or "").strip())
    if (not translated or "\n" in translated or len(translated) > 40 or
            not re.search(r"[\u3400-\u9fff]", translated)):
        return name
    learned_skill_put(name, translated)
    return translated


def translate_skill_names(names, c):
    glossary = load_skill_glossary()
    results = []
    for name in names:
        key = name.strip().lower()
        translated = glossary.get(key) or learned_skill_get(key)
        if translated is None:
            translated = translate_unknown_skill(name, c)
        results.append(translated)
    return results


def learned_library_get(name):
    db = cache_connection()
    if db is None:
        return None


def load_library_glossary():
    global LIBRARY_GLOSSARY
    if LIBRARY_GLOSSARY is not None:
        return LIBRARY_GLOSSARY
    try:
        raw = json.loads(LIBRARY_GLOSSARY_FILE.read_text(encoding="utf-8"))
        LIBRARY_GLOSSARY = {str(k).strip().lower(): str(v).strip() for k, v in raw.items() if str(v).strip()}
    except Exception as e:
        log("library glossary load failed: %r" % e, True)
        LIBRARY_GLOSSARY = {}
    return LIBRARY_GLOSSARY
    try:
        db.execute("CREATE TABLE IF NOT EXISTS library_glossary(source_name TEXT PRIMARY KEY, translated_name TEXT NOT NULL, updated_at INTEGER NOT NULL)")
        row = db.execute("SELECT translated_name FROM library_glossary WHERE source_name=?", (name.lower(),)).fetchone()
        return row[0] if row else None
    except Exception as e:
        log("library glossary read failed: %r" % e, True)
        return None


def learned_library_put(name, translated):
    db = cache_connection()
    if db is None:
        return
    try:
        db.execute("CREATE TABLE IF NOT EXISTS library_glossary(source_name TEXT PRIMARY KEY, translated_name TEXT NOT NULL, updated_at INTEGER NOT NULL)")
        db.execute("INSERT OR REPLACE INTO library_glossary(source_name,translated_name,updated_at) VALUES(?,?,?)",
                   (name.lower(), translated, int(time.time())))
        db.commit()
    except Exception as e:
        log("library glossary write failed: %r" % e, True)


def translate_library_batch(names, c):
    """Translate ordered book titles, recursively shrinking any malformed batch."""
    if not names:
        return []
    if len(names) == 1:
        return [translate_piece(names[0], c)]
    prompt = (
        "Translate each English book title below into Chinese. Output exactly one translated "
        "title per line, in the same order. Do not add numbering or explanations.\nEnglish:\n" +
        "\n".join(names) + "\nChinese:"
    )
    timeout = max(3, float(c.get("request_timeout_seconds", 25)))
    try:
        response = http_post("/v1/chat/completions", {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": min(1024, max(192, len(prompt))),
            "temperature": 0.0,
            "repeat_penalty": 1.1,
            "stream": False,
        }, timeout)
        choices = response.get("choices") or []
        content = ((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        lines = [re.sub(r"^\s*(?:[-*]\s+|\d+[.)：:]\s*)", "", line).strip() for line in lines]
        if len(lines) != len(names) or any(not line for line in lines):
            raise RuntimeError("LIBRARY_BATCH_LINE_COUNT_MISMATCH")
        return [to_traditional_characters(line) for line in lines]
    except Exception:
        midpoint = len(names) // 2
        return translate_library_batch(names[:midpoint], c) + translate_library_batch(names[midpoint:], c)


def translate_library_titles(names, c):
    static_glossary = load_library_glossary()
    results = {}
    unknown = []
    for name in names:
        key = name.strip().lower()
        if key in results:
            continue
        learned = static_glossary.get(key) or learned_library_get(key)
        if learned is not None:
            results[key] = learned
        else:
            unknown.append(name.strip())
    # Small batches bound latency and make a malformed response cheap to retry.
    for start in range(0, len(unknown), 12):
        batch = unknown[start:start + 12]
        translated = translate_library_batch(batch, c)
        for source_name, translated_name in zip(batch, translated):
            results[source_name.lower()] = translated_name
            learned_library_put(source_name, translated_name)
    return [results[name.strip().lower()] for name in names]


def is_library_catalog(text):
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return bool(lines and LIBRARY_HEADER.match(lines[0]) and
                sum(bool(LIBRARY_ROW.match(line)) for line in lines[1:]) >= 3)


def translate_library_catalog(text, c):
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    parsed, titles = [], []
    for line in lines:
        if LIBRARY_HEADER.match(line):
            parsed.append(("header", line))
            continue
        row = LIBRARY_ROW.match(line)
        if row:
            parsed.append(("row", row.groups()))
            titles.append(row.group(4))
        elif not line.strip():
            parsed.append(("raw", line))
        else:
            raise RuntimeError("LIBRARY_UNRECOGNIZED_ROW")
    translated_titles = iter(translate_library_titles(titles, c))
    output = []
    for kind, value in parsed:
        if kind == "header":
            indent = value[:len(value) - len(value.lstrip())]
            output.append(indent + "書號 - 書名")
        elif kind == "row":
            indent, book_id, separator, _title, trailing = value
            output.append(indent + book_id + separator + next(translated_titles) + trailing)
        else:
            output.append(value)
    result = "\n".join(output)
    if len(result.split("\n")) != len(lines):
        raise RuntimeError("LIBRARY_FINAL_LINE_COUNT_MISMATCH")
    source_ids = [match.group(2) for line in lines if (match := LIBRARY_ROW.match(line))]
    result_ids = [match.group(2) for line in result.split("\n") if (match := LIBRARY_ROW.match(line))]
    if source_ids != result_ids:
        raise RuntimeError("LIBRARY_FINAL_ID_MISMATCH")
    return result


def translate_skills_block(text, c):
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    parsed, names = [], []
    for line in lines:
        match = SKILL_LINE.match(line)
        if match:
            parsed.append(("skill", match.groups()))
            names.append(match.group(2).strip())
        elif line.strip() in SKILL_SECTIONS:
            parsed.append(("section", line.strip()))
        elif line.strip() == "You know the following skills:":
            parsed.append(("header", None))
        else:
            parsed.append(("raw", line))
    if len(names) < 1:
        raise RuntimeError("SKILLS_PARSE_EMPTY")
    translated_names = iter(translate_skill_names(names, c))
    output = []
    for kind, value in parsed:
        if kind == "header":
            output.append("你會以下技能：")
        elif kind == "section":
            output.append(SKILL_SECTIONS[value] + " | " + value)
        elif kind == "skill":
            indent, _name, rating, percent = value
            zh_name = next(translated_names)
            output.append("%s%s，%s %s" % (indent, zh_name, SKILL_RATINGS[rating.lower()], percent))
        else:
            output.append(value)
    result = "\n".join(output)
    ok, reason = translation_sanity_ok(text, result)
    if not ok:
        raise RuntimeError("SKILLS_FINAL_SANITY_" + reason)
    return result


def is_practice_table(text):
    """Recognize the skill-practice requirement table by shape, not its contents."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    nonempty = [line.strip() for line in lines if line.strip()]
    # A movement/combat status row can arrive in the same quiet-period batch.
    # The table header must still be near the start, followed by real columns
    # and skill rows; this remains much stricter than matching a word alone.
    if not nonempty or not any(PRACTICE_HEADER.match(line) for line in nonempty[:3]):
        return False
    return (sum(bool(PRACTICE_COLUMN_HEADER.match(line)) for line in nonempty) >= 1 and
            sum(bool(PRACTICE_LINE.match(line)) for line in lines) >= 1)


def translate_practice_table(text, c):
    """Translate a practice table while preserving every requirement field verbatim."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    parsed, names = [], []
    for line in lines:
        header = PRACTICE_HEADER.match(line.strip())
        skill = PRACTICE_LINE.match(line)
        if header:
            parsed.append(("header", header.group(1)))
        elif PRACTICE_COLUMN_HEADER.match(line.strip()):
            # Keep the ASCII table geometry stable for history navigation.
            parsed.append(("columns", line))
        elif skill:
            parsed.append(("skill", skill.groups()))
            names.append(skill.group(2).strip())
        elif line.strip():
            parsed.append(("prose", line))
        else:
            parsed.append(("raw", line))
    if not names:
        raise RuntimeError("PRACTICE_PARSE_EMPTY")

    translated_names = iter(translate_skill_names(names, c))
    output = []
    for kind, value in parsed:
        if kind == "header":
            output.append("你還剩 %s 次練習。" % ("1" if value.lower() == "one" else value))
        elif kind == "columns":
            output.append(value.replace("Int Wis Chr Lvl", "智力 智慧 魅力 等級"))
        elif kind == "skill":
            indent, _name, separator, rating, rating_separator, suffix = value
            zh_name = next(translated_names)
            zh_rating = "尚未學會" if rating.lower() == "not learned" else SKILL_RATINGS[rating.lower()]
            # suffix contains all requirements, class codes and percentages;
            # never ask the model to reproduce or rewrite it.
            output.append(indent + zh_name + separator + zh_rating + rating_separator + suffix)
        elif kind == "prose":
            # Section headings and the explanatory footer repeat across every
            # practice attempt. Cache them independently while reconstructing
            # dynamic counts, ratings and requirements from the fresh table.
            translated = PRACTICE_FIXED_PROSE.get(value.strip()) or translate_cached_phrase(value, c)
            output.append(" ".join(translated.splitlines()).strip())
        else:
            output.append(value)

    result = "\n".join(output)
    if len(result.split("\n")) != len(lines):
        raise RuntimeError("PRACTICE_FINAL_LINE_COUNT_MISMATCH")
    ok, reason = translation_sanity_ok(text, result)
    if not ok:
        raise RuntimeError("PRACTICE_FINAL_SANITY_" + reason)
    return result


def parse_class_skill_table(text):
    """Parse the fixed-width table emitted by ``skills <class>``."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines or not CLASS_SKILL_HEADER.match(lines[0].strip()):
        return None
    rows = []
    for line in lines[1:]:
        if not line.strip():
            rows.append(("", "", ""))
            continue
        # Alter Aeon fixes Mage at column 28, Known at 67 and Dependencies at
        # 73. Validate the class/numeric field so unrelated prose cannot be
        # mistaken for this table merely because it is long.
        if len(line) < 73:
            return None
        name = line[:28].strip()
        fields = line[28:73]
        dependency = line[73:].strip()
        if not name or not re.fullmatch(r"[\s\d%+.,-]+", fields):
            return None
        rows.append((name, fields, dependency))
    substantive = [row for row in rows if row[0]]
    return (lines, rows) if len(substantive) >= 2 else None


def is_class_skill_table(text):
    return parse_class_skill_table(text) is not None


def translate_class_skill_table(text, c):
    """Translate skill and dependency names without exposing table rows to LMT."""
    parsed = parse_class_skill_table(text)
    if parsed is None:
        raise RuntimeError("CLASS_SKILL_TABLE_PARSE_FAILED")
    lines, rows = parsed
    names = []
    for name, _fields, dependency in rows:
        if name:
            names.append(name)
        dep_match = CLASS_SKILL_DEPENDENCY.match(dependency)
        if dep_match and dep_match.group(1).strip():
            names.append(dep_match.group(1).strip())
    unique_names = list(dict.fromkeys(name.lower() for name in names))
    translated_names = translate_skill_names(unique_names, c)
    translated = dict(zip(unique_names, translated_names))

    output = ["技能／咒語  法師 牧師 盜賊 戰士 死靈法師 德魯伊 等級 練習 已知 依賴關係"]
    importance = {"important": "重要", "helpful": "有幫助"}
    for name, fields, dependency in rows:
        if not name:
            output.append("")
            continue
        suffix = " ".join(fields.split())
        dep_match = CLASS_SKILL_DEPENDENCY.match(dependency)
        if dep_match:
            dep_name, rating = dep_match.groups()
            dep_name = dep_name.strip()
            rendered_dependency = translated.get(dep_name.lower(), dep_name) if dep_name else ""
            rendered_dependency = (rendered_dependency + " " if rendered_dependency else "") + "（%s）" % importance[rating.lower()]
        else:
            # Preserve an unknown future dependency shape verbatim rather than
            # risking loss of a requirement.
            rendered_dependency = dependency
        rendered = translated.get(name.lower(), name)
        output.append(" ".join(part for part in (rendered, suffix, rendered_dependency) if part))

    result = "\n".join(output)
    if len(result.split("\n")) != len(lines):
        raise RuntimeError("CLASS_SKILL_TABLE_LINE_COUNT_MISMATCH")
    if numeric_values(text) != numeric_values(result):
        raise RuntimeError("CLASS_SKILL_TABLE_NUMERIC_MISMATCH")
    return result


def is_direction_listing(text):
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return len(lines) >= 2 and any(DIRECTION_LINE.match(line) for line in lines)


def translate_direction_listing(text, c):
    """Preserve navigation result rows that small models often omit."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output = []
    for line in lines:
        direction = DIRECTION_LINE.match(line)
        if direction:
            indent, code, trailing = direction.groups()
            rendered = DIRECTION_NAMES.get(code.upper(), code.upper())
            output.append("%s方向 -> %s%s" % (indent, rendered, trailing))
            continue
        arrow = re.match(r"^(.*?)(\s*->\s*)(.*?)$", line)
        if arrow and arrow.group(1).strip() and arrow.group(3).strip():
            left = translate_piece(arrow.group(1).strip(), c)
            right = translate_piece(arrow.group(3).strip(), c)
            output.append(left + arrow.group(2) + right)
        elif line.strip():
            output.append(translate_piece(line, c))
        else:
            output.append("")
    result = "\n".join(output)
    if len(result.split("\n")) != len(lines):
        raise RuntimeError("DIRECTION_FINAL_LINE_COUNT_MISMATCH")
    if not any("方向 ->" in line for line in result.split("\n")):
        raise RuntimeError("DIRECTION_FINAL_MARKER_MISSING")
    return result


def translate_structured_line_block(text, c):
    """Translate a non-skills structured block with one output per input line."""
    source_lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    block_kind = structured_block_kind(text)
    if not block_kind:
        raise RuntimeError("STRUCTURED_START_MARKER_MISSING")
    output = []
    for source_line in source_lines:
        if not source_line.strip():
            output.append("")
            continue
        fixed_header = STRUCTURED_EXACT_HEADERS.get(source_line.strip())
        fixed_timestamp = translate_inventory_timestamp(source_line)
        try:
            translated_line = fixed_header or fixed_timestamp
            if translated_line is None:
                # Preserve item quantities deterministically.  A model may
                # render "6 gold coins" as Chinese words (六枚金幣), which is
                # readable but violates the numeric integrity contract and used
                # to make the entire ground/inventory block fall back.  Keeping
                # the prefix outside the model also lets different quantities
                # share the same cached item-name translation.
                quantity = re.match(r"^(\s*(?:\(\s*\d+\s*\)|\d+)\s+)(.+)$", source_line)
                cache_source = quantity.group(2) if quantity else source_line
                translated_body = reviewed_phrase_translation(cache_source) or cache_get(cache_source, c)
                if translated_body is None:
                    translated_body = translate_piece(cache_source, c, force_robust=True)
                    cache_put(cache_source, translated_body, c)
                translated_line = (quantity.group(1) if quantity else "") + translated_body
                # A short line such as "freak 2!" has only one numeric item,
                # so the general per-piece sanity guard may legitimately not
                # run its block-level numeric rule.  Enforce it here before
                # assembling a mixed combat + container block; otherwise one
                # damaged line makes the final guard reject every translated
                # combat event and item in the block.
                if numeric_values(source_line) and not numeric_items_preserved(source_line, translated_line):
                    raise RuntimeError("structured_line_numeric_items_missing")
                cache_put(source_line, translated_line, c)
        except Exception as error:
            # Preserve a single problematic line in English. One novel combat
            # fragment must not discard an otherwise valid inventory block.
            log("structured line fallback: %r source=%r" % (error, source_line[:160]), True)
            translated_line = source_line
        # A single item must remain a single history entry even if the model
        # decorates its answer with an unexpected line break.
        output.append(" ".join(translated_line.splitlines()).strip())
    result = "\n".join(output)
    # Every structured source row was translated (or fell back to its complete
    # English row) independently above.  Validate the structure itself here.
    # Applying the prose length-ratio/repetition guard to the reconstructed
    # block incorrectly rejects legitimate inventories containing many copies
    # of one item, especially when its Chinese name is much shorter.
    result_lines = result.split("\n")
    if len(result_lines) != len(source_lines):
        raise RuntimeError("STRUCTURED_FINAL_LINE_COUNT_MISMATCH")
    if any(source_line.strip() and not translated_line.strip()
           for source_line, translated_line in zip(source_lines, result_lines)):
        raise RuntimeError("STRUCTURED_FINAL_BLANK_ROW")
    if not numeric_items_preserved(text, result):
        raise RuntimeError("STRUCTURED_FINAL_NUMERIC_ITEMS_MISSING")
    return result


def translate_inventory_block(text, c):
    """Backward-compatible name used by inventory regression tests."""
    return translate_structured_line_block(text, c)


def seed_structured_line_cache(source, translated, c):
    """Learn safe row pairs from a valid whole-block cache hit."""
    if not structured_block_kind(source):
        return 0
    source_lines = str(source).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    translated_lines = str(translated).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(source_lines) != len(translated_lines):
        return 0
    stored = 0
    for source_line, translated_line in zip(source_lines, translated_lines):
        if not source_line.strip() or not translated_line.strip():
            continue
        if source_line.strip() in STRUCTURED_EXACT_HEADERS:
            continue
        ok, _reason = translation_sanity_ok(source_line, translated_line)
        if ok:
            cache_put(source_line, translated_line, c)
            stored += 1
    return stored


def is_quest_structured_block(text):
    value = str(text)
    return bool(
        is_quest_list_block(value)
        or re.search(r"^Quest Name:\s*", value, re.MULTILINE)
        or re.search(r"^Complete the \d+ tasks below to gain a reward\.$", value, re.MULTILINE)
    )


def is_quest_list_block(text):
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(lines) < 2:
        return False
    first = lines[0].strip().lower()
    active = first == "you have discovered or been given the following quests:"
    available = "following quests are available to you at this time:" in first
    nearby = first == "there are the following unfinished quests nearby:"
    return bool((active or available or nearby) and any(
        QUEST_LIST_ROW.match(line) or QUEST_AVAILABLE_ROW.match(line) or NEARBY_QUEST_ROW.match(line)
        for line in lines[1:]
    ))


def is_job_list_block(text):
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return bool(
        len(lines) >= 2
        and lines[0].strip().lower() == "currently accepted jobs:"
        and any(JOB_LIST_ROW.match(line) for line in lines[1:])
    )


def translate_task_list_block(text, c, kind):
    """Render job and quest lists one source row at a time for NVDA history."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output = []
    exact = {
        "You have discovered or been given the following quests:": "你已發現或接到以下任務：",
        "Currently accepted jobs:": "目前已接受的工作：",
        "There are the following unfinished quests nearby:": "附近有以下尚未完成的任務：",
        "Num  Level  Name": "編號　等級　名稱",
        "You can see more information with the 'quest info' command.": "你可以使用 'quest info' 指令查看更多資訊。",
        "You can see more information with the 'job info' command.": "你可以使用 'job info' 指令查看更多資訊。",
        "(There are no quests listed here, but there may be quests nearby.": "（這裡沒有列出任務，但附近可能有任務。",
        "Use the 'quest nearby' command to see nearby quests.)": "請使用 'quest nearby' 指令查看附近任務。）",
        "For details on a quest, use 'quest nearby'. For example, 'quest nearby 1'.":
            "若要查看任務詳情，請使用 'quest nearby'，例如 'quest nearby 1'。",
    }
    for line in lines:
        value = line.strip()
        quest_row = QUEST_LIST_ROW.match(line) if kind == "quest" else None
        available_row = QUEST_AVAILABLE_ROW.match(line) if kind == "quest" else None
        nearby_row = NEARBY_QUEST_ROW.match(line) if kind == "quest" else None
        job_row = JOB_LIST_ROW.match(line) if kind == "job" else None
        if value in exact:
            indent = line[:len(line) - len(line.lstrip())]
            output.append(indent + exact[value])
        elif quest_row:
            indent, number, description, active, trailing = quest_row.groups()
            zh = translate_piece(description.strip(), c, force_robust=True)
            output.append("%s任務 %s - %s%s%s" % (
                indent, number, zh, " [進行中]" if active else "", trailing
            ))
        elif available_row:
            indent, number, description, trailing = available_row.groups()
            zh = translate_piece(description.strip(), c, force_robust=True)
            output.append("%s[%s] %s%s" % (indent, number, zh, trailing))
        elif nearby_row:
            indent, number, level, description, trailing = nearby_row.groups()
            zh = translate_piece(description.strip(), c, force_robust=True)
            output.append("%s%s　%s　%s%s" % (indent, number, level, zh, trailing))
        elif job_row:
            indent, number, description, trailing = job_row.groups()
            zh = translate_piece(description.strip(), c, force_robust=True)
            output.append("%s工作 %s：%s%s" % (indent, number, zh, trailing))
        elif not value:
            output.append("")
        else:
            fixed = deterministic_translate(value)
            output.append(fixed if fixed is not None else translate_piece(value, c, force_robust=True))
    result = "\n".join(output)
    if len(result.split("\n")) != len(lines):
        raise RuntimeError("TASK_LIST_FINAL_LINE_COUNT_MISMATCH")
    ok, reason = translation_sanity_ok(text, result)
    if not ok:
        raise RuntimeError("TASK_LIST_FINAL_SANITY_" + reason)
    return result


def is_nearby_direction_listing(text):
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return bool(
        len(lines) >= 2
        and any(NEARBY_DIRECTION_HEADER.match(line) for line in lines)
        and any(NEARBY_DIRECTION_ROW.match(line) for line in lines)
    )


def translate_nearby_direction_listing(text, c):
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output = []
    for line in lines:
        header = NEARBY_DIRECTION_HEADER.match(line)
        row = NEARBY_DIRECTION_ROW.match(line)
        if header:
            output.append("方向　附近%s" % ("地標" if header.group(1).lower() == "landmarks" else "商店"))
        elif row:
            indent, direction, description, trailing = row.groups()
            zh = translate_piece(description.strip(), c, force_robust=True)
            output.append("%s%s　%s%s" % (indent, DIRECTION_NAMES[direction.upper()], zh, trailing))
        elif line.strip():
            fixed = deterministic_translate(line.strip())
            output.append(fixed if fixed is not None else translate_piece(line.strip(), c, force_robust=True))
        else:
            output.append("")
    result = "\n".join(output)
    if len(result.split("\n")) != len(lines):
        raise RuntimeError("NEARBY_DIRECTION_FINAL_LINE_COUNT_MISMATCH")
    return result


def is_dense_item_table(text):
    lines = [line for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    if len(lines) < 6:
        return False
    matched = sum(bool(DENSE_ITEM_ROW.match(line)) for line in lines)
    return matched >= 5 and matched / len(lines) >= 0.70


def translate_dense_item_table(text, c):
    """Preserve large headerless equipment/item result sets row by row."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output = []
    for line in lines:
        row = DENSE_ITEM_ROW.match(line)
        if row:
            prefix, item, trailing = row.groups()
            zh = cache_get(item.strip(), c)
            if zh is None:
                zh = translate_piece(item.strip(), c, force_robust=True)
                cache_put(item.strip(), zh, c)
            output.append(prefix + " ".join(zh.splitlines()).strip() + trailing)
        elif line.strip():
            fixed = deterministic_translate(line.strip())
            output.append(fixed if fixed is not None else translate_piece(line.strip(), c, force_robust=True))
        else:
            output.append("")
    result = "\n".join(output)
    if len(result.split("\n")) != len(lines):
        raise RuntimeError("DENSE_ITEM_FINAL_LINE_COUNT_MISMATCH")
    return result


def is_nearby_map_listing(text):
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(lines) < 2:
        return False
    first = lines[0].strip()
    return bool(
        (NEARBY_MAP_SEARCH_HEADER.match(first) or first == "You consult your maps and find nearby...")
        and any(line.strip() == "Level      Name/Direction" for line in lines[1:])
    )


def translate_nearby_map_listing(text, c):
    """Preserve the nearby-area table as one accessible row per source row."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output = []
    for line in lines:
        value = line.strip()
        search = NEARBY_MAP_SEARCH_HEADER.match(value)
        row = NEARBY_MAP_ROW.match(line)
        if search:
            output.append("你查閱地圖，尋找附近名稱包含「%s」的區域：" % search.group(1))
        elif value == "You consult your maps and find nearby...":
            output.append("你查閱地圖，找到附近區域：")
        elif value == "Level      Name/Direction":
            output.append("等級　名稱／方向")
        elif row:
            indent, level, area_name, distance, direction, trailing = row.groups()
            zh_name = translate_piece(area_name.strip(), c, force_robust=True)
            zh_distance = NEARBY_MAP_DISTANCES[distance.lower()]
            zh_direction = NEARBY_MAP_DIRECTIONS[direction.lower()]
            output.append("%s等級 %s　%s，位於%s方，%s。%s" % (
                indent, level, zh_name, zh_direction, zh_distance, trailing
            ))
        elif value == "To see location of nearby major cities, try 'nearby city'.":
            output.append("若要查看附近主要城市的位置，請輸入 'nearby city'。")
        elif not value:
            output.append("")
        else:
            fixed = deterministic_translate(value)
            output.append(fixed if fixed is not None else translate_piece(value, c, force_robust=True))
    result = "\n".join(output)
    if len(result.split("\n")) != len(lines):
        raise RuntimeError("NEARBY_MAP_FINAL_LINE_COUNT_MISMATCH")
    ok, reason = translation_sanity_ok(text, result)
    if not ok:
        raise RuntimeError("NEARBY_MAP_FINAL_SANITY_" + reason)
    return result


def translate_quest_structured_block(text, c):
    """Preserve quest metadata/status and translate only semantic fields."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output, paragraph = [], []

    def flush_paragraph():
        if not paragraph:
            return
        chunks = semantic_display_chunks("\n".join(paragraph))
        if chunks:
            output.extend(translate_semantic_units(
                [("translate", chunk) for chunk in chunks], c, "quest_detail"
            ).splitlines())
        paragraph[:] = []

    for line in lines:
        stripped = line.strip()
        fixed = deterministic_translate(stripped) if stripped else None
        quest_row = QUEST_LIST_ROW.match(line)
        detail = QUEST_DETAIL_FIELD.match(stripped)
        if fixed or quest_row or detail or not stripped:
            flush_paragraph()
        if not stripped:
            output.append("")
        elif fixed:
            indent = line[:len(line) - len(line.lstrip())]
            output.append(indent + fixed)
        elif quest_row:
            indent, number, description, active, trailing = quest_row.groups()
            zh_description = translate_piece(description.strip(), c, force_robust=True)
            zh_active = " [進行中]" if active else ""
            output.append("%s任務 %s - %s%s%s" % (indent, number, zh_description, zh_active, trailing))
        elif detail:
            label, value = detail.groups()
            zh_label = QUEST_DETAIL_LABELS[label.lower()]
            if label.lower() in {"area level", "creator", "editors", "approximate difficulty (scale from 1 to 10)"}:
                zh_value = value
            else:
                zh_value = translate_semantic_units(
                    [("translate", value)], c, "quest_field"
                ) if value else ""
            output.append("%s：%s" % (zh_label, zh_value))
        else:
            paragraph.append(line)
    flush_paragraph()
    result = "\n".join(output)
    if not result.strip():
        raise RuntimeError("QUEST_FINAL_EMPTY")
    if numeric_values(text) and not numeric_items_preserved(text, result):
        raise RuntimeError("QUEST_FINAL_NUMERIC_ITEMS_MISSING")
    return result


def is_character_status_block(text):
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return (len(lines) >= 4 and lines[0].startswith("You are ") and
            bool(re.match(r"^You are level \d+ with \d+ practices?\s+\(\d+ hours?\)$", lines[1].strip())))


def is_counter_stats_block(text):
    value = str(text).strip()
    return value.startswith("Counters since ") and "To reset the counters, type scm reset." in value


def translate_counter_stats_block(text):
    """Render the fixed scm counter table without model inference."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output = []
    patterns = (
        (r"^Counters since (.+)$", lambda g: "自 %s 起的統計：" % g[0]),
        (r"^You have been hit (\d+) times, dodged (\d+), and parried (\d+)\. Which means you avoided (\d+)percent of hits\.$",
         lambda g: "你被擊中 %s 次、閃避 %s 次、招架 %s 次，總共避開百分之 %s 的攻擊。" % g),
        (r"^You attacked (\d+) times\. Mobs dodged (\d+), and parried (\d+)\. (\d+)percent of your attacks avoided\.$",
         lambda g: "你攻擊了 %s 次；怪物閃避 %s 次、招架 %s 次，你有百分之 %s 的攻擊被避開。" % g),
        (r"^Your armor absorbed (\d+) hits\.$", lambda g: "你的護甲吸收了 %s 次攻擊。" % g[0]),
        (r"^You've killed (\d+) mobs this session, and fled (\d+) times\.$", lambda g: "本次遊戲中你擊殺了 %s 隻怪物，並逃跑 %s 次。" % g),
        (r"^You've casted a total of (\d+) spells\.$", lambda g: "你總共施放了 %s 次法術。" % g[0]),
        (r"^You have disarmed a total of (\d+) mobs\.$", lambda g: "你總共繳械了 %s 隻怪物。" % g[0]),
        (r"^You stole a total of (\d+) gold this session\.$", lambda g: "本次遊戲中你總共偷取了 %s 枚金幣。" % g[0]),
        (r"^You became better (\d+) times\.$", lambda g: "你的能力提升了 %s 次。" % g[0]),
        (r"^You got (\d+) necromancer teeth, and shattered (\d+)\.$", lambda g: "你取得了 %s 顆死靈法師牙齒，並擊碎了 %s 顆。" % g),
        (r"^To reset the counters, type scm reset\.$", lambda g: "若要重設計數器，請輸入 scm reset。"),
    )
    for line in lines:
        value = line.strip()
        rendered = None
        for pattern, formatter in patterns:
            match = re.match(pattern, value, re.I)
            if match:
                rendered = formatter(match.groups())
                break
        if rendered is None:
            # Format changes must remain visible in English, never disappear.
            rendered = line
        output.append(rendered)
    result = "\n".join(output)
    ok, reason = translation_sanity_ok(text, result)
    if not ok:
        raise RuntimeError("COUNTERS_FINAL_SANITY_" + reason)
    return result


def status_spell_names(names):
    """Use static/learned glossary only; status output must never wait per spell."""
    glossary = load_skill_glossary()
    output = {}
    for name in names:
        key = name.strip().lower()
        output[key] = glossary.get(key) or learned_skill_get(key) or name
    return output


def translate_character_status_block(text, c):
    """Render score/status output deterministically and preserve every number."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    spell_names = [m.group(1) for line in lines if (m := STATUS_SPELL_LINE.match(line.strip()))]
    spell_map = status_spell_names(spell_names)
    output = []
    for line_index, line in enumerate(lines):
        value = line.strip()
        match = re.match(r"^You are (.+?)\s*$", value)
        if line_index == 0 and match:
            output.append("你是 %s" % match.group(1)); continue
        match = re.match(r"^You are level (\d+) with (\d+) practices?\s+\((\d+) hours?\)$", value)
        if match:
            output.append("你是 %s 級，有 %s 點練習點數（%s 小時）。" % match.groups()); continue
        match = re.match(r"^You are carrying (\d+)/(\d+) items with weight (\d+)/(\d+) pounds\.\s+Encumbrance:\s+(\d+)%$", value)
        if match:
            output.append("你攜帶 %s／%s 件物品，重量 %s／%s 磅；負重率 %s%%。" % match.groups()); continue
        match = re.match(r"^You have collected (\d+) acorns\.$", value)
        if match:
            output.append("你已收集 %s 顆橡實。" % match.group(1)); continue
        match = re.match(r"^You have (\d+)/(\d+) hit, (\d+)/(\d+) mana, (\d+)/(\d+) movement\.$", value)
        if match:
            output.append("血量 %s／%s，法力 %s／%s，體力 %s／%s。" % match.groups()); continue
        if re.match(r"^(?:Str|Int|Wis|Dex|Con|Chr):", value):
            parts = re.findall(r"(Str|Int|Wis|Dex|Con|Chr):\s*(-?\d+)", value)
            if parts:
                output.append("  ".join("%s：%s" % (STATUS_STAT_NAMES[name], number) for name, number in parts)); continue
        match = re.match(r"^Your levels are:\s*(.*)$", value)
        if match:
            output.append("你的職業等級：%s" % match.group(1)); continue
        match = re.match(r"^Hitroll:\s*(-?\d+)\s+Damroll:\s*(-?\d+)$", value)
        if match:
            output.append("命中加值：%s  傷害加值：%s" % match.groups()); continue
        match = re.match(r"^Armor:\s*(-?\d+)\s+\(you are wearing (.*?)\)$", value, re.I)
        if match:
            armor_kind = {"light armor": "輕甲", "medium armor": "中甲", "heavy armor": "重甲"}.get(match.group(2).lower(), match.group(2))
            output.append("護甲：%s（你穿著%s）。" % (match.group(1), armor_kind)); continue
        match = re.match(r"^You have (\d+) 'get out of death free' cards?!$", value)
        if match:
            output.append("你有 %s 張免死卡！" % match.group(1)); continue
        if value == "You are hiding.": output.append("你正躲藏著。"); continue
        if value == "You are not hungry.": output.append("你不餓。"); continue
        match = re.match(r"^Alignment:\s*(-?\d+)\s+\(You are (neutral|good|evil)\.\)$", value, re.I)
        if match:
            alignment = {"neutral": "中立", "good": "善良", "evil": "邪惡"}[match.group(2).lower()]
            output.append("陣營值：%s（你是%s陣營。）" % (match.group(1), alignment)); continue
        if value == "You are not suffering from any major debilitating conditions.":
            output.append("你沒有受到任何重大的衰弱狀態影響。"); continue
        spell = STATUS_SPELL_LINE.match(value)
        if spell:
            name, details = spell.groups()
            zh_name = spell_map.get(name.lower(), name)
            if not details:
                output.append("法術「%s」" % zh_name); continue
            maintained = re.match(r"^maintained, level (\d+)$", details, re.I)
            remaining = re.match(r"^(.*?), level (\d+)$", details, re.I)
            if maintained:
                output.append("法術「%s」，維持中，等級 %s" % (zh_name, maintained.group(1))); continue
            if remaining:
                duration = remaining.group(1)
                duration = re.sub(r"\btwo hours\b", "2 小時", duration, flags=re.I)
                duration = re.sub(r"\b(\d+) hours?\b", r"\1 小時", duration, flags=re.I)
                duration = re.sub(r"\b(\d+) minutes? remaining\b", r"剩餘 \1 分鐘", duration, flags=re.I)
                output.append("法術「%s」，%s，等級 %s" % (zh_name, duration, remaining.group(2))); continue
        if not value:
            output.append(""); continue
        deterministic = deterministic_translate(value)
        output.append(deterministic if deterministic is not None else translate_piece(value, c, force_robust=True))
    result = "\n".join(output)
    if len(result.split("\n")) != len(lines):
        raise RuntimeError("STATUS_FINAL_LINE_COUNT_MISMATCH")
    ok, reason = translation_sanity_ok(text, result)
    if not ok:
        raise RuntimeError("STATUS_FINAL_SANITY_" + reason)
    return result


def translate(text,c):
    if has_embedded_tip_block(text):
        return translate_embedded_tip_block(text, c)
    # Quest lists are tables, not quest-detail prose.  Check them before the
    # broader quest detector so nearby/available rows keep their header,
    # number, level and instruction lines instead of being merged by a cloud
    # provider as one paragraph.
    if is_quest_list_block(text):
        return translate_task_list_block(text, c, "quest")
    # Quest detail blocks often contain several quoted NPC conversations.
    # Preserve their deterministic fields before the generic wrapped-dialogue
    # detector can claim the entire quest as one prose request.
    if is_quest_structured_block(text):
        return translate_quest_structured_block(text, c)
    if is_wrapped_dialogue_block(text):
        return translate_wrapped_dialogue_block(text, c)
    relative_history = translate_relative_history_timestamp(text, c)
    if relative_history is not None:
        return relative_history
    xp_history = translate_xp_history_line(text, c)
    if xp_history is not None:
        return xp_history
    if is_semantic_event_block(text):
        return translate_semantic_event_block(text, c)
    if is_action_template_block(text):
        return translate_action_template_block(text, c)
    if is_combat_template_block(text):
        return translate_combat_template_block(text, c)
    if is_quest_help_block(text):
        return translate_quest_help_block(text)
    if is_available_level_skills_block(text):
        return translate_available_level_skills_block(text, c)
    if is_room_preview_block(text):
        return translate_room_preview_block(text, c)
    if is_quest_information_block(text):
        return translate_quest_information_block(text, c)
    deterministic = deterministic_translate(text)
    if deterministic is not None:
        return deterministic
    fixed_timestamp = translate_inventory_timestamp(text)
    if fixed_timestamp:
        return fixed_timestamp
    if is_counter_stats_block(text):
        return translate_counter_stats_block(text)
    if is_character_status_block(text):
        return translate_character_status_block(text, c)
    if is_character_creation_welcome(text):
        return translate_character_creation_welcome(text)
    if is_login_menu(text):
        return translate_login_menu(text, c)
    if is_help_search_listing(text):
        return translate_help_search_listing(text, c)
    if is_friends_listing(text):
        return translate_friends_listing(text, c)
    if is_skill_help_detail(text):
        return translate_skill_help_detail(text, c)
    if is_equipment_advice(text):
        return translate_equipment_advice(text, c)
    if is_room_with_doors(text):
        return translate_room_with_doors(text, c)
    if is_tip_block(text):
        return translate_tip_block(text, c)
    if is_syntax_help_block(text):
        return translate_syntax_help_block(text, c)
    if is_book_text_block(text):
        return translate_book_text_block(text, c)
    if is_mobs_in_room_listing(text):
        return translate_mobs_in_room_listing(text, c)
    if is_scan_listing(text):
        return translate_scan_listing(text, c)
    if is_nearby_map_listing(text):
        return translate_nearby_map_listing(text, c)
    if is_nearby_direction_listing(text):
        return translate_nearby_direction_listing(text, c)
    if is_dense_item_table(text):
        return translate_dense_item_table(text, c)
    if is_job_list_block(text):
        return translate_task_list_block(text, c, "job")
    if str(text).lstrip().startswith("You know the following skills:"):
        return translate_skills_block(text, c)
    if is_class_skill_table(text):
        return translate_class_skill_table(text, c)
    if is_practice_table(text):
        return translate_practice_table(text, c)
    if is_library_catalog(text):
        return translate_library_catalog(text, c)
    if is_direction_listing(text):
        return translate_direction_listing(text, c)
    if structured_block_kind(text):
        return translate_structured_line_block(text, c)
    if is_numeric_report_block(text):
        return translate_numeric_report_block(text, c)
    if has_repeated_source_lines(text):
        return translate_repeated_line_block(text, c)
    if has_deterministic_lines(text):
        return translate_mixed_deterministic_block(text, c)
    if has_trailing_independent_rows(text):
        return translate_trailing_independent_rows(text, c)
    if is_room_prose_candidate(text):
        return translate_room_prose_cached(text, c)
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if sum(1 for line in lines if re.match(r"^\s*\d+\)\s*", line)) >= 3:
        rendered = []
        for line in lines:
            numbered = re.match(r"^(\s*\d+\)\s*)(.+)$", line)
            if numbered:
                rendered.append(numbered.group(1) + completion_once(numbered.group(2), c, 128))
            elif line.strip():
                rendered.append(translate_piece(line, c))
            else:
                rendered.append("")
        result = "\n".join(rendered)
        ok, reason = translation_sanity_ok(text, result)
        if not ok:
            raise RuntimeError("LMT_FINAL_SANITY_" + reason)
        return result
    # Large blocks are proactively chunked so they cannot silently hit the
    # decoder limit after a long wait.  Short normal gameplay stays one call.
    chunks = split_source(text, 650) if len(text) > 900 else [text]
    robust = len(text) >= 180 or text.count("\n") >= 3
    result = "\n".join(translate_piece(chunk, c, force_robust=robust) for chunk in chunks)
    ok, reason = translation_sanity_ok(text, result)
    if not ok:
        raise RuntimeError("LMT_FINAL_SANITY_" + reason)
    return result


def trace_record(request_id, status, source, result="", elapsed=0.0, error=""):
    """Local diagnostic record. Contains MUD text; never auto-shared."""
    try:
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "request_id": str(request_id),
            "status": str(status),
            "elapsed_seconds": round(float(elapsed), 3),
            "source": str(source),
            "result": str(result),
            "error": str(error),
            "engine": "+".join(sorted(TRANSLATION_ENGINES_USED)) or "local",
        }
        rotate_log_if_needed(TRACE_LOG, TRACE_LOG_MAX_BYTES)
        with TRACE_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass

def atomic_write(path,text):
    tmp=path.with_suffix(".tmp");tmp.write_text(text,encoding="utf-8");os.replace(tmp,path)


def decode_request_payload(data):
    """Decode UTF-8 output capture or a legacy MUSHclient input code page."""
    try:
        return bytes(data).decode("utf-8")
    except UnicodeDecodeError:
        pass
    encodings = ["mbcs", locale.getpreferredencoding(False), "cp950", "gb18030"]
    fallback = None
    for encoding in dict.fromkeys(encodings):
        try:
            candidate = bytes(data).decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
        if fallback is None:
            fallback = candidate
        if contains_cjk(candidate):
            return candidate
    if fallback is not None:
        return fallback
    return bytes(data).decode("utf-8", "replace")

def run():
    global SERVER_START_THREAD, SERVER_SHUTTING_DOWN, SERVER_ALLOW_AUTOTUNE
    INBOX.mkdir(exist_ok=True);OUTBOX.mkdir(exist_ok=True)
    if not acquire_lock():return
    log("LMT Q4 WORKER START pid=%s python=%s"%(os.getpid(),sys.executable),True)
    try:
        if cloud_translation_candidates():
            SERVER_ALLOW_AUTOTUNE = True
            SERVER_START_THREAD = threading.Thread(
                target=start_server_in_background, name="mushz-lmt-startup", daemon=True
            )
            SERVER_START_THREAD.start()
            log("worker ready - cloud primary; LMT-60 tuning in background",True)
        else:
            start_server()
            log("worker ready - LMT-60 1.7B Q4",True)
        while session_alive():
            jobs=sorted(INBOX.glob("req_*.txt"))
            if not jobs:
                time.sleep(.05);continue
            job=jobs[0];rid=job.stem[4:];out=OUTBOX/("res_"+rid+".txt")
            try:
                raw=decode_request_payload(base64.b64decode(job.read_text(encoding="ascii")))
                TRANSLATION_ENGINES_USED.clear()
                if raw.startswith(CONTROL_CLEAR_RECENT_CACHE):
                    requested = raw[len(CONTROL_CLEAR_RECENT_CACHE):].strip() or "5"
                    removed = clear_recent_translation_cache(int(requested))
                    result = "已清除最近 %d 筆翻譯快取。請重新觸發內容以重新翻譯。" % removed
                    trace_record(rid,"CONTROL",raw,result,0.0,"")
                    atomic_write(out,"OK\n"+result)
                    continue
                if raw.startswith(CONTROL_TRANSLATE_OUTGOING_CHAT):
                    source = raw[len(CONTROL_TRANSLATE_OUTGOING_CHAT):]
                    t = time.perf_counter()
                    result = translate_outgoing_chat(source, config())
                    elapsed = time.perf_counter() - t
                    trace_record(rid, "OUTGOING_ZH_EN", source, result, elapsed, "")
                    atomic_write(out, "OK\n" + result)
                    continue
                if raw == CONTROL_CHECK_API:
                    result = cloud_api_report()
                    trace_record(rid, "CONTROL", raw, result, 0.0, "")
                    atomic_write(out, "OK\n" + result)
                    continue
                c=config(); result=None if should_bypass_whole_block_cache(raw) else cache_get(raw,c)
                if result is None:
                    t=time.perf_counter()
                    result=to_traditional_characters(translate(raw,c))
                    result=normalize_npc_names(raw,result)
                    elapsed=time.perf_counter()-t
                    log("translated id=%s chars=%d in %.3fs"%(rid,len(raw),elapsed))
                    trace_record(rid,"OK",raw,result,elapsed,"")
                    cache_put(raw,result,c)
                else:
                    mark_translation_engine("cache")
                    seed_structured_line_cache(raw, result, c)
                    cached_result=result
                    result=normalize_npc_names(raw,result)
                    if result != cached_result:
                        cache_put(raw,result,c)
                    trace_record(rid,"CACHE",raw,result,0.0,"")
                atomic_write(out,"OK\n"+result)
            except Exception as e:
                elapsed=(time.perf_counter()-t) if "t" in locals() else 0.0
                log("request %s ERROR %r"%(rid,e),True)
                try: trace_record(rid,"ERROR",raw if "raw" in locals() else "","",elapsed,repr(e))
                except Exception: pass
                atomic_write(out,"ERR\n"+str(e))
            finally:
                try:job.unlink()
                except OSError:pass
    finally:
        SERVER_SHUTTING_DOWN = True
        stop_candidate(ACTIVE_CANDIDATE)
        if SERVER_START_THREAD is not None and SERVER_START_THREAD.is_alive():
            SERVER_START_THREAD.join(timeout=5)
        if CACHE_CONNECTION is not None:
            try:CACHE_CONNECTION.close()
            except Exception:pass
        if SERVER_PROCESS is not None:
            try:SERVER_PROCESS.terminate();SERVER_PROCESS.wait(timeout=5)
            except Exception:
                try:SERVER_PROCESS.kill()
                except Exception:pass
        try:LOCK.unlink()
        except OSError:pass
        log("worker stopped",True)

if __name__=="__main__":run()
