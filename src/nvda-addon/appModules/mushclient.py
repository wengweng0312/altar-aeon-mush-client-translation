# -*- coding: utf-8 -*-
# Merged Mush Client accessibility app module and optional Translation Mode review navigation.

import os
import json
import re
import tempfile
import time

import api
import appModuleHandler
import controlTypes
import core
import globalCommands
import oleacc
import scriptHandler
import textInfos
import ui
from keyboardHandler import KeyboardInputGesture
from NVDAObjects import NVDAObject, NVDAObjectTextInfo
from NVDAObjects.window import Window


REVIEW_STATE_FILE = os.path.join(tempfile.gettempdir(), "mushz_translation_review_mode.txt")
REVIEW_ENTRY_FILE = os.path.join(tempfile.gettempdir(), "mushz_translation_review_entry.txt")
REVIEW_DIAGNOSTIC_FILE = os.path.join(tempfile.gettempdir(), "mushz_translation_nvda_diagnostic.jsonl")
REVIEW_DIAGNOSTIC_LIMIT = 2 * 1024 * 1024
REVIEW_DIAGNOSTIC_ARCHIVES = 5
_reviewRequestGeneration = 0


def _rotateTranslationDiagnostic():
	try:
		if not os.path.isfile(REVIEW_DIAGNOSTIC_FILE) or os.path.getsize(REVIEW_DIAGNOSTIC_FILE) < REVIEW_DIAGNOSTIC_LIMIT:
			return
		oldest = REVIEW_DIAGNOSTIC_FILE + ".%d" % REVIEW_DIAGNOSTIC_ARCHIVES
		if os.path.exists(oldest):
			os.remove(oldest)
		for number in range(REVIEW_DIAGNOSTIC_ARCHIVES - 1, 0, -1):
			source = REVIEW_DIAGNOSTIC_FILE + ".%d" % number
			if os.path.exists(source):
				os.replace(source, REVIEW_DIAGNOSTIC_FILE + ".%d" % (number + 1))
		os.replace(REVIEW_DIAGNOSTIC_FILE, REVIEW_DIAGNOSTIC_FILE + ".1")
	except OSError:
		pass


def _translationDiagnostic(event, **fields):
	"""Best-effort metadata-only diagnostics; never interrupt NVDA review."""
	try:
		_rotateTranslationDiagnostic()
		record = {
			"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
			"monotonic": round(time.monotonic(), 6),
			"pid": os.getpid(),
			"event": str(event),
		}
		for key, value in fields.items():
			if isinstance(value, (str, int, float, bool)) or value is None:
				record[str(key)] = value
		with open(REVIEW_DIAGNOSTIC_FILE, "a", encoding="utf-8", newline="\n") as output:
			output.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
	except Exception:
		pass

_properNamePattern = re.compile(
	r"\b(?:Sir|Lady|King|Queen|Captain|Doctor|Fast|Old)?\s*"
	r"[A-Z][A-Za-z'-]+(?:\s+(?:(?:of|the|and)\s+)?[A-Z][A-Za-z'-]+){0,4}\b"
)
_quotedCommandPattern = re.compile(
	r"['\"]((?:quest|job|task|sale|nearby|look|examine|read|search|ask|say|give|get|put|drop|"
	r"wear|remove|skills?|inventory|map|areas?)"
	r"(?:\s+[^'\"]+){0,4})['\"]",
	re.I,
)
_speakerPattern = re.compile(
	r"^(.+?)\s+(?:says|asks|exclaims|tells you|whispers|shouts),?\s*['\"]",
	re.I,
)
_actionPattern = re.compile(
	r"^You\s+(?:put|place)\s+(.+?)\s+(?:in|into|on)\s+(.+?)[.!]?$|"
	r"^You\s+(?:get|take)\s+(.+?)\s+from\s+(.+?)[.!]?$|"
	r"^You\s+give\s+(.+?)\s+to\s+(.+?)[.!]?$",
	re.I,
)
_bulkGetPattern = re.compile(r"^You get \d+ items? from (.+?):\s*(.+)$", re.I)
_entityEventPattern = re.compile(
	r"^\*?(.+?)\s+(?:is here|stands\b.*|patrols\b.*|guards\b.*|watches\b.*|"
	r"has arrived|arrives|leaves(?:\s+\w+)?|walks in|flies in|enters|disappears|"
	r"has been\b.*|is hovering\b.*|is floating\b.*|is lying\b.*|is resting here|is DEAD!)[.!]?$",
	re.I,
)
_directionalActorMovementPattern = re.compile(
	r"^(.+?)\s+(leaves?|flies?|walks?|runs?|crawls?|rides?|marches?|wanders?|"
	r"stalks?|sneaks?|slips?|hurries|charges?|retreats?|flees|departs?|moves?|"
	r"travels?|proceeds?|heads?|goes|swims?|drifts?)\s+"
	r"(?:(?:off|away)\s+)?(?:(?:to|toward|towards|for)\s+(?:the\s+)?)?"
	r"(north|south|east|west|up|down|northeast|northwest|southeast|southwest)"
	r"[.!]?$",
	re.I,
)
_nonActorMovementHeads = {
	"path", "road", "street", "trail", "way", "track", "tunnel", "passage",
	"passageway", "hall", "hallway", "corridor", "bridge", "stairs", "stairway",
	"stream", "river", "creek", "channel", "cave", "cavern", "light", "smoke",
	"wall", "fence", "ledge", "slope", "valley", "forest", "door", "gate",
	"exit", "entrance", "portal",
}
_landmarkPattern = re.compile(
	r"\b((?:[A-Za-z'-]+\s+){0,4}(?:research guild|guild|port|harbor|shop|inn|bank|"
	r"temple|tower|gate|road|way|caves?|forest|courtyard|workshop))\b"
)
_fixtureSubjectPattern = re.compile(
	r"\b(?:A|An|The|Some)\s+([A-Za-z][A-Za-z' -]{0,100}?)\s+"
	r"(?:has been|have been|can be (?:seen|appreciated|found)|is|are|was|were|stands?|sits?|"
	r"lies?|hangs?|hovers?|floats?|rests?|blocks?|leads?|leading|opens?|extends?|rises?|juts?|"
	r"looms?|marks?|covers?|fills?|contains?|waits?|guards?|patrols?|grows?|runs?|winds?|"
	r"dominates?|occupies?|forms?|creates?|reveals?|provides?|holds?|bears?|sticks?)\b",
	re.I,
)
_bareFixtureSubjectPattern = re.compile(
	r"(?:^|(?<=[.!?])\s+)([A-Z][A-Za-z'-]*(?:\s+[a-z][A-Za-z'-]*){0,4})\s+"
	r"(?:juts?|stands?|sits?|lies?|hangs?|hovers?|floats?|blocks?|leads?|opens?|extends?|"
	r"rises?|looms?|covers?|grows?|winds?)\b"
)
_articlePattern = re.compile(r"^(?:a|an|the|some)\s+", re.I)
_flagsPattern = re.compile(r"\s*\([^)]*\)\s*$")
_keyStopNames = {
	"a", "an", "the", "you", "your", "in", "on", "at", "for", "from",
	"to", "mobs", "some", "there", "this", "that", "now", "english",
	"bring", "once", "wandering", "find", "use",
}
_landmarkLeadingNoise = {
	"a", "an", "the", "to", "from", "in", "inside", "outside", "at", "on",
	"find", "use", "before", "after", "toward", "towards", "near", "nearby", "once",
	"into", "these", "those", "this", "that", "my", "our", "your",
	"of", "about", "around", "through", "couple", "few", "several", "many",
}
_fixtureAbstractHeads = {
	"fact", "feeling", "idea", "impression", "former", "latter", "nothing",
	"everything", "anything", "work", "view", "silence", "air", "size",
}
_fixtureInternalNoise = {
	"this", "these", "those", "you", "your", "my", "our", "like", "knew",
	"seem", "seems", "seemed", "look", "looks", "looked", "could", "would", "should",
}
_properNameBoundaryWords = {
	"A", "An", "The", "You", "This", "That", "These", "Those", "There",
	"In", "On", "At", "To", "From", "For", "With", "Set", "Once", "While",
}
_roomTitleChineseSuffixes = {
	"way": ("之路", "道路", "路", "道"),
	"road": ("道路", "之路", "路", "道"),
	"street": ("街道", "大街", "街"),
	"streets": ("街道", "大街", "街"),
	"path": ("小徑", "路徑", "道路", "小路", "路", "徑"),
	"trail": ("小徑", "古道", "道路", "路", "徑"),
	"shop": ("商店", "藥店", "店鋪", "店"),
	"town": ("城鎮", "小鎮", "城市", "鎮", "城"),
	"city": ("城市", "城鎮", "城"),
	"waypoint": ("路標", "航點", "傳送點"),
	"barracks": ("軍營", "兵營"),
	"workshop": ("工作坊", "工坊"),
	"guild": ("公會", "協會"),
	"forest": ("森林", "樹林"),
	"cave": ("洞穴", "洞窟", "山洞"),
	"caves": ("洞穴", "洞窟", "山洞"),
	"cavern": ("洞穴", "洞窟", "洞"),
	"hospital": ("醫院",),
	"hall": ("大廳", "廳堂", "廳"),
	"room": ("房間", "室"),
	"chamber": ("房間", "密室", "室"),
	"gate": ("大門", "城門", "門"),
	"bridge": ("橋樑", "橋"),
}


def _isCJK(character):
	if not character:
		return False
	code = ord(character)
	return (
		0x3400 <= code <= 0x4DBF
		or 0x4E00 <= code <= 0x9FFF
		or 0xF900 <= code <= 0xFAFF
	)


def _cleanEnglishKey(value):
	value = value.strip().strip("'\".,;:!?")
	while _flagsPattern.search(value):
		value = _flagsPattern.sub("", value).strip()
	return _articlePattern.sub("", value).strip()


def _cleanLandmarkKey(value):
	words = _cleanEnglishKey(value).split()
	while words and words[0].lower() in _landmarkLeadingNoise:
		words.pop(0)
	if not words:
		return ""
	suffixSize = 2 if len(words) >= 2 and [word.lower() for word in words[-2:]] == ["research", "guild"] else 1
	suffix = words[-suffixSize:]
	prefix = words[:-suffixSize]
	titled = []
	for word in reversed(prefix):
		if word[:1].isupper():
			titled.insert(0, word)
		else:
			break
	if titled:
		return " ".join(titled + suffix)
	while prefix and prefix[-1].lower() in _landmarkLeadingNoise:
		prefix.pop()
	adjective = prefix[-1:] if prefix else []
	if adjective and (adjective[0].lower() in _landmarkLeadingNoise or re.search(r"(?:ed|ing)$", adjective[0], re.I)):
		adjective = []
	return " ".join(adjective + suffix)


def _cleanFixtureSubject(value):
	"""Reduce a grammatical subject to the phrase a player can type."""
	value = _cleanEnglishKey(value)
	value = re.split(r"\s+(?:which|that|who|whose)\s+", value, maxsplit=1, flags=re.I)[0]
	value = re.split(r"\s+(?:on|in|at|near|with|to|between|beside|behind|before)\s+", value, maxsplit=1, flags=re.I)[0]
	return value.strip()


def _addEnglishKey(output, value):
	value = _cleanEnglishKey(value)
	if not value or value.lower() in _keyStopNames:
		return
	if value.lower() not in {item.lower() for item in output}:
		output.append(value)


def _safeEntityKey(value):
	cleaned = _cleanEnglishKey(value)
	if not cleaned or len(cleaned) > 120 or len(cleaned.split()) > 12:
		return False
	if re.match(r"^(?:you|your|there|this|that|it|while|when)\b", cleaned, re.I):
		return False
	return not re.search(r"[.!?]['\"]?$", value.strip())


def _englishRoomTitleIndex(rows):
	"""Mirror the worker's conservative room-title boundary detection."""
	prefixEnd = re.compile(r"[.!?][\"')\]]*$")
	safePrefix = re.compile(
		r"^(?:(?:In the next room you see|Nearby you see):|Your next cheapest level\b.*)$",
		re.I,
	)
	nonTitle = re.compile(r"\b(?:casts?|attacks?|strikes?|kills?|is DEAD|assists?)\b", re.I)
	periodStart = re.compile(
		r"^(?:A|An|The|Near|Inside|Outside|At|In|Before|Beyond|Overlooking|"
		r"Climbing|Heading|Following)\b",
		re.I,
	)
	for index, row in enumerate(rows[:9]):
		if index >= len(rows) - 1 or not row or len(row) > 70:
			continue
		if re.match(r"^(?:you|your|there|exits?|mobs?|level|experience)\b", row, re.I):
			continue
		if nonTitle.search(row):
			continue
		if index and not all(prefixEnd.search(prefix) or safePrefix.match(prefix) for prefix in rows[:index]):
			continue
		ordinaryTitle = not re.search(r"[.!?:;]$", row)
		periodTitle = (
			row.endswith(".")
			and len(row[:-1].split()) <= 12
			and (index == 0 or periodStart.match(row))
		)
		if not (ordinaryTitle or periodTitle):
			continue
		body = rows[index + 1:index + 5]
		hasImmediateDisplayWrap = len(body) >= 2 and any(
			len(line) >= 35 and not prefixEnd.search(line) for line in body[:3]
		)
		hasSemanticBody = bool(body) and bool(prefixEnd.search(body[0]))
		if hasImmediateDisplayWrap or hasSemanticBody:
			return index
	return -1


def _isDirectionalActorMovement(text):
	"""True for an actor leaving in a direction, not scenery extending that way."""
	match = _directionalActorMovementPattern.match(text.strip())
	if not match:
		return False
	subject = _cleanEnglishKey(match.group(1))
	words = subject.lower().split()
	if not words or words[0] in {"you", "your", "there", "it"}:
		return False
	return words[-1] not in _nonActorMovementHeads


def _translationEnglishKeys(source):
	"""Extract command-useful English without exposing the complete original."""
	keys = []
	text = source.strip()
	# Direction already tells the player what happened.  Exposing the actor's
	# English name on ordinary departure messages is noise, regardless of
	# whether the actor leaves, flies, crawls, rides, or uses another locomotion
	# verb.  Keep landscape sentences such as "The road runs east" out of this.
	if _isDirectionalActorMovement(text):
		return []
	bulk = _bulkGetPattern.match(text)
	if bulk:
		_addEnglishKey(keys, bulk.group(1))
		for item in bulk.group(2).split(","):
			_addEnglishKey(keys, item)
		return keys
	action = _actionPattern.match(text)
	if action:
		for value in action.groups():
			if value:
				_addEnglishKey(keys, value)
		return keys
	speaker = _speakerPattern.match(text)
	if speaker:
		_addEnglishKey(keys, speaker.group(1))
	entityEvent = _entityEventPattern.match(text)
	if entityEvent:
		_addEnglishKey(keys, entityEvent.group(1))
		# The subject is the command-useful target.  Do not leak a location or
		# proper name later in the same NPC status sentence instead.
		return keys
	rows = [row.strip() for row in text.splitlines() if row.strip()]
	roomTitleIndex = _englishRoomTitleIndex(rows)
	isRoom = roomTitleIndex >= 0
	if isRoom:
		_addEnglishKey(keys, rows[roomTitleIndex])
	if len(rows) == 1 and _safeEntityKey(text):
		if re.search(r"\s+\d+%(?:\s|$)", text):
			_addEnglishKey(keys, re.sub(r"\s+\d+%.*$", "", text).strip())
		elif not re.search(r"^(?:Password|Enter Selection|Logging in)\b", text, re.I):
			_addEnglishKey(keys, text)
	for command in _quotedCommandPattern.findall(text):
		_addEnglishKey(keys, command)
	flattened = " ".join(text.splitlines())
	if isRoom:
		flattened = " ".join(rows[:roomTitleIndex] + [rows[roomTitleIndex] + "."] + rows[roomTitleIndex + 1:])
	for match in _fixtureSubjectPattern.finditer(flattened):
		candidate = _cleanFixtureSubject(match.group(1))
		words = candidate.split()
		lowerWords = {word.lower() for word in words}
		if (words and len(words) <= 6 and words[0].lower() not in _fixtureAbstractHeads
				and words[-1].lower() not in _fixtureAbstractHeads
				and not (lowerWords & _fixtureInternalNoise)):
			_addEnglishKey(keys, candidate)
	for match in _bareFixtureSubjectPattern.finditer(flattened):
		candidate = _cleanFixtureSubject(match.group(1))
		words = candidate.split()
		lowerWords = {word.lower() for word in words}
		if (words and len(words) <= 6 and words[0].lower() not in {"a", "an", "the", "some"}
				and words[-1].lower() not in _fixtureAbstractHeads
				and not (lowerWords & _fixtureInternalNoise)):
			_addEnglishKey(keys, candidate)
	# Work on repaired prose rather than physical MUD rows.  Otherwise a wrap
	# such as "dark forest\nYou..." becomes the false proper name
	# "dark forest You".
	for row in re.split(r"(?<=[.!?])\s+", flattened):
		for landmark in _landmarkPattern.findall(row):
			_addEnglishKey(keys, _cleanLandmarkKey(landmark))
		for name in _properNamePattern.findall(row):
			cleaned = _cleanEnglishKey(name)
			words = cleaned.split()
			for index, word in enumerate(words[1:], 1):
				if word in _properNameBoundaryWords:
					words = words[:index]
					cleaned = " ".join(words)
					break
			titled = bool(words and words[0].lower() in {"sir", "lady", "king", "queen", "captain", "doctor"})
			if (len(words) >= 2 or titled) and words and words[0].lower() not in _keyStopNames and not cleaned.isupper():
				_addEnglishKey(keys, cleaned)
	compact = [
		key for key in keys
		if not any(key.lower() != other.lower() and key.lower() in other.lower() for other in keys)
	]
	return compact[:6]


def _splitMergedChineseRoomTitle(chinese, englishTitle):
	"""Split a merged translated room title only when its type gives a safe boundary."""
	firstSentenceEnd = re.search(r"[。！？!?]", chinese)
	searchEnd = min(60, firstSentenceEnd.start() if firstSentenceEnd else len(chinese))
	titleType = englishTitle.strip().lower().split()[-1:] or [""]
	for suffix in _roomTitleChineseSuffixes.get(titleType[0], ()):
		position = chinese.find(suffix, 0, searchEnd)
		if position >= 0:
			end = position + len(suffix)
			title = chinese[:end].strip()
			remainder = chinese[end:].strip()
			if title and remainder:
				return title, remainder
	return "", chinese


def _translationSentenceOffsets(text, offset):
	"""Return a Chinese sentence range, or None for NVDA's normal word logic."""
	if not text or offset < 0 or offset >= len(text):
		return None
	for start, end in _translationChineseSentenceRanges(text):
		if start <= offset < end:
			return start, end
	return None


def _translationChineseSentenceRanges(text):
	"""Return sentence ranges from the Chinese half of a bilingual entry."""
	if not text:
		return []
	chineseEnd = text.find("|")
	if chineseEnd < 0:
		chineseEnd = len(text)
	terminators = "。！？!?\n\r"
	ranges = []
	start = 0
	for position in range(chineseEnd):
		if text[position] not in terminators:
			continue
		end = position + 1
		trimmedStart = start
		while trimmedStart < end and text[trimmedStart].isspace():
			trimmedStart += 1
		trimmedEnd = end
		while trimmedEnd > trimmedStart and text[trimmedEnd - 1].isspace():
			trimmedEnd -= 1
		if any(_isCJK(character) for character in text[trimmedStart:trimmedEnd]):
			ranges.append((trimmedStart, trimmedEnd))
		start = end
	trimmedStart = start
	while trimmedStart < chineseEnd and text[trimmedStart].isspace():
		trimmedStart += 1
	trimmedEnd = chineseEnd
	while trimmedEnd > trimmedStart and text[trimmedEnd - 1].isspace():
		trimmedEnd -= 1
	if any(_isCJK(character) for character in text[trimmedStart:trimmedEnd]):
		ranges.append((trimmedStart, trimmedEnd))
	return ranges


def _translationReviewSegments(text):
	"""Return Chinese sentences first, followed by English words."""
	segments = _translationChineseSentenceRanges(text)
	divider = text.find("|") if text else -1
	if divider < 0:
		return segments
	for match in re.finditer(r"\S+", text[divider + 1:]):
		start = divider + 1 + match.start()
		end = divider + 1 + match.end()
		segments.append((start, end))
	return segments


def _translationChinesePresentationLines(chinese, english):
	"""Format Chinese for review without changing the stored translation."""
	chinese = chinese.strip()
	if not chinese:
		return []
	if re.match(r"^[^\r\n]+?\s+(?:says(?:\s+in\s+an?\s+[^,\r\n]{1,80}\s+voice)?|asks),\s*['\"]", english.strip(), re.I) or re.match(
		r"^[^\r\n]+?\s+tells?\s+[^\r\n]+?,\s*['\"]", english.strip(), re.I
	):
		return [" ".join(chinese.split())]
	lines = []
	englishLines = [line.strip() for line in english.splitlines() if line.strip()]
	roomTitleIndex = _englishRoomTitleIndex(englishLines)
	isRoom = roomTitleIndex >= 0
	# Room output commonly has a short, punctuation-free English title on its
	# own first line. Translation may join its Chinese title to the first
	# sentence with one space, so split that title only in this presentation.
	if isRoom:
		# Preserve a real translated title row when the worker supplied one,
		# while treating all later newlines as terminal display wrapping.
		titleExtracted = False
		physicalLines = [line.strip() for line in chinese.splitlines() if line.strip()]
		if (len(physicalLines) > roomTitleIndex
				and len(physicalLines[roomTitleIndex]) <= 60
				and not re.search(r"[。！？!?:;]$", physicalLines[roomTitleIndex])):
			lines.extend(physicalLines[:roomTitleIndex])
			lines.append(physicalLines[roomTitleIndex])
			chinese = " ".join(physicalLines[roomTitleIndex + 1:])
			titleExtracted = True
		if not titleExtracted:
			title, remainder = _splitMergedChineseRoomTitle(chinese, englishLines[roomTitleIndex])
			if title:
				lines.append(title)
				chinese = remainder
				titleExtracted = True
		firstSpace = re.search(r"\s+", chinese)
		firstTerminator = re.search(r"[。！？!?\r\n]", chinese)
		if not titleExtracted and firstSpace and (not firstTerminator or firstSpace.start() < firstTerminator.start()):
			title = chinese[:firstSpace.start()].strip()
			remainder = chinese[firstSpace.end():].strip()
			if 1 < len(title) <= 40 and any(_isCJK(character) for character in title) and any(
				_isCJK(character) for character in remainder
			):
				lines.append(title)
				chinese = remainder
		# MUD room prose is physically wrapped to the screen width.  Those
		# newlines are not sentence boundaries and must not fragment review.
		chinese = " ".join(chinese.splitlines())
		chinese = re.sub(r"\s+", " ", chinese).strip()
	start = 0
	# Keep closing quotation/bracket marks attached to the sentence they close.
	# Otherwise text ending in ？” or 。』 creates a useless one-character line.
	for match in re.finditer(r"(?:[。！？!?][”’\"'）】》〕』」]*|\r?\n)", chinese):
		end = match.end()
		line = chinese[start:end].strip()
		if line:
			lines.append(line)
		start = end
	tail = chinese[start:].strip()
	if tail:
		lines.append(tail)
	return lines


def _translationPairedDialogueLines(chinese, english):
	"""Pair safely aligned sentences from a translated NPC dialogue."""
	englishValue = " ".join(english.split()).strip()
	chineseValue = " ".join(chinese.split()).strip()
	if not chineseValue or not englishValue:
		return []
	if not (
		re.match(r"^[^\r\n]+?\s+(?:says(?:\s+in\s+an?\s+[^,\r\n]{1,80}\s+voice)?|asks|replies|exclaims),\s*['\"]", englishValue, re.I)
		or re.match(r"^[^\r\n]+?\s+tells?\s+[^\r\n]+?,\s*['\"]", englishValue, re.I)
	):
		return []

	def splitSentences(value, terminators, requireWhitespace):
		rows = []
		start = 0
		pattern = r"[" + re.escape(terminators) + r"]+[”’\"'）】》〕』」]*"
		if requireWhitespace:
			pattern += r"(?=\s|$)"
		for match in re.finditer(pattern, value):
			row = value[start:match.end()].strip()
			if row:
				rows.append(row)
			start = match.end()
		tail = value[start:].strip()
		if tail:
			rows.append(tail)
		return rows

	chineseRows = splitSentences(chineseValue, "。！？!?", False)
	englishRows = splitSentences(englishValue, ".!?", True)
	# Sentence pairing is presentation-only, but a wrong pairing is still more
	# confusing than one long line. Fail closed whenever either side differs.
	if len(chineseRows) < 2 or len(chineseRows) != len(englishRows) or len(chineseRows) > 20:
		return []
	return [chineseRow + " | " + englishRow for chineseRow, englishRow in zip(chineseRows, englishRows)]


def _translationPairedRoomLines(chinese, english):
	"""Pair an aligned room only when movement, title and prose all agree."""
	englishRows = [line.strip() for line in english.splitlines() if line.strip()]
	titleIndex = _englishRoomTitleIndex(englishRows)
	if titleIndex < 0:
		return []

	def sentences(rows):
		value = " ".join(rows).strip()
		if not value:
			return []
		return [row.strip() for row in re.split(r"(?<=[.!?])\s+", value) if row.strip()]

	englishUnits = (
		sentences(englishRows[:titleIndex]) +
		[englishRows[titleIndex]] +
		sentences(englishRows[titleIndex + 1:])
	)
	chineseUnits = [line.strip() for line in chinese.splitlines() if line.strip()]
	if len(englishUnits) < 2 or len(chineseUnits) != len(englishUnits):
		return []
	return [chineseRow + " | " + englishRow for chineseRow, englishRow in zip(chineseUnits, englishUnits)]


def _translationPairedMonsterLoreLines(chinese, english):
	"""Pair a line-preserving monster-lore report without guessing."""
	englishRows = [line.strip() for line in english.splitlines() if line.strip()]
	if not any(re.match(r"^You use your knowledge of monster lore:", row, re.I) for row in englishRows):
		return []
	chineseRows = [line.strip() for line in chinese.splitlines() if line.strip()]
	# LMT commonly joins the report heading and the following creature label.
	# Split that one known boundary, but only accept it if every resulting row
	# aligns exactly with the original report.
	for index, row in enumerate(chineseRows):
		if not re.search(r"怪物(?:知識|傳說)", row):
			continue
		match = re.match(r"^(.+?[：:])\s*(.+)$", row)
		if match:
			chineseRows[index:index + 1] = [match.group(1).strip(), match.group(2).strip()]
		break
	if len(chineseRows) < 2 or len(chineseRows) != len(englishRows):
		return []
	return [chineseRow + " | " + englishRow for chineseRow, englishRow in zip(chineseRows, englishRows)]


def _translationTaskListLines(english):
	"""Return task-list rows only for worker-owned line-preserving formats."""
	rows = [line.strip() for line in english.splitlines() if line.strip()]
	if len(rows) < 2:
		return []
	first = rows[0].lower()
	isTaskList = (
		first == "you have discovered or been given the following quests:"
		or "following quests are available to you at this time:" in first
		or first == "there are the following unfinished quests nearby:"
		or first == "currently accepted jobs:"
	)
	return rows if isTaskList else []


def _translationPairedTaskListLines(chinese, english):
	"""Pair task tables by exact row; never reinterpret rows as prose."""
	englishRows = _translationTaskListLines(english)
	if not englishRows:
		return []
	chineseRows = [line.strip() for line in chinese.splitlines() if line.strip()]
	if len(chineseRows) != len(englishRows):
		return []
	return [chineseRow + " | " + englishRow for chineseRow, englishRow in zip(chineseRows, englishRows)]


def _translationPairedSalesLines(chinese, english):
	"""Pair the line-preserving credit sale table without prose guessing."""
	englishRows = [line.strip() for line in english.splitlines() if line.strip()]
	if not (
		len(englishRows) >= 3
		and englishRows[0] == "There are the following sales running:"
		and englishRows[-1] == "Use the 'credit buy' command to take advantage of these deals."
	):
		return []
	chineseRows = [line.strip() for line in chinese.splitlines() if line.strip()]
	if len(chineseRows) != len(englishRows):
		return []
	return [chineseRow + " | " + englishRow for chineseRow, englishRow in zip(chineseRows, englishRows)]


def _translationPairedSyntaxLines(chinese, english):
	"""Keep Syntax command tables as one bilingual row per source row."""
	englishRows = [line.strip() for line in english.splitlines() if line.strip()]
	if len(englishRows) < 2 or not englishRows[0].startswith("Syntax:"):
		return []
	chineseRows = [line.strip() for line in chinese.splitlines() if line.strip()]
	if len(chineseRows) != len(englishRows):
		return []
	return [chineseRow + " | " + englishRow for chineseRow, englishRow in zip(chineseRows, englishRows)]


def _translationPairedProseLines(chinese, english):
	"""Pair ordinary narrative/dialogue only when every sentence aligns."""
	def splitSentences(value, terminators, requireWhitespace):
		value = " ".join(value.split()).strip()
		rows, start = [], 0
		pattern = r"[" + re.escape(terminators) + r"]+[”’\"'）】》〕』」]*"
		if requireWhitespace:
			pattern += r"(?=\s|$)"
		for match in re.finditer(pattern, value):
			row = value[start:match.end()].strip()
			if row:
				rows.append(row)
			start = match.end()
		tail = value[start:].strip()
		if tail:
			rows.append(tail)
		return rows

	chineseRows = splitSentences(chinese, "。！？!?", False)
	englishRows = splitSentences(english, ".!?", True)
	if len(chineseRows) < 2 or len(chineseRows) != len(englishRows) or len(chineseRows) > 20:
		return []
	return [chineseRow + " | " + englishRow for chineseRow, englishRow in zip(chineseRows, englishRows)]


def _isHelpUsageCommand(row):
	"""Match command syntax following Usage, including multi-word spells."""
	value = row.strip()
	if not value or len(value) > 140 or re.search(r"[.!?]", value):
		return False
	return bool(re.fullmatch(
		r"'?\s*[a-z][a-z0-9'-]*(?:\s+(?:[a-z][a-z0-9'-]*|-[a-z][a-z0-9-]*|<[^>]+>|\[[^\]]+\]))*\s*'?",
		value,
	))


def _translationHelpSemanticLines(english):
	"""Mirror the worker's stable help fields, commands and prose units."""
	rows = [line.strip() for line in english.splitlines() if line.strip()]
	# The worker accepts every complete Help page, not only skill/spell pages.
	# Keeping the old narrow test here made ordinary pages fall through to the
	# 600-character emergency splitter, which paired unrelated Chinese and
	# English fragments in review mode.
	if len(rows) < 3 or not any(row.startswith("Keywords are:") for row in rows[:2]):
		return []
	metadata = re.compile(
		r"^(Showing page \d+\.|Keywords are:|Skill:|Spell:|"
		r"\((?:critical|important|helpful|useful|obscure|guild)\)|"
		r"\(Can Be (?:Groupcast|Maintained|Bloodcast)\)|\(Requires Favor\)|"
		r"Group:|Speed:|Damage Type:|Damage:|Usage:|Syntax:|Format:|"
		r"Summary:|Possible Values:|Profession$|Guild:|"
		r"There are \d+ other help pages that may be related to your search\.|"
		r"See '.*' for a list\.|See also,?|"
		r"You can create the (?:spell|skill) .* on the following consumables:|"
		r"You can use .* while:)",
		re.I,
	)
	units, prose = [], []
	inUsage = False
	inCommandTable = False
	afterUsable = False
	inPossibleValues = False

	def flushProse():
		if not prose:
			return
		current = []
		for line in prose:
			current.append(line)
			if re.search(r"[.!?][\"')\]]*\s*$", line):
				units.append(" ".join(current))
				current[:] = []
		if current:
			units.append(" ".join(current))
		prose[:] = []

	for row in rows:
		if metadata.match(row):
			flushProse()
			units.append(row)
			inUsage = row.lower() in {"usage:", "syntax:", "format:"}
			inCommandTable = inUsage
			afterUsable = bool(re.match(r"^You can use .* while:$", row, re.I))
			inPossibleValues = row.lower() == "possible values:"
			continue
		if inPossibleValues and re.match(r"^\d+\s*-\s*.+", row):
			flushProse()
			units.append(row)
			continue
		commandDescription = re.fullmatch(r"(.+?)(\s+(?:--?|:)\s+)(.+)", row)
		if commandDescription and (inUsage or inCommandTable) and _isHelpUsageCommand(commandDescription.group(1)):
			flushProse()
			units.append(row)
			continue
		if (inUsage or inCommandTable) and _isHelpUsageCommand(row):
			flushProse()
			units.append(row)
			continue
		inUsage = False
		inPossibleValues = False
		if afterUsable:
			flushProse()
			units.append(row)
			afterUsable = False
			continue
		# Spellgroup/skillgroup trees are already reconstructed by the worker as
		# one row per skill.  Preserve the same boundary here so a complete tree
		# is not collapsed back into one giant review line.
		if re.fullmatch(r".+?\s{2,}\d+\s+(?:mag|cle|thi|war|nec|dru)", row, re.I):
			flushProse()
			units.append(row)
			continue
		if re.match(r"^-\s+.+", row):
			flushProse()
			units.append(row)
			continue
		if re.fullmatch(r"(?:For )?Examples?,?", row, re.I):
			flushProse()
			units.append(row)
			continue
		if row.endswith(":") and len(row) <= 100:
			flushProse()
			units.append(row)
			inUsage = row.lower().endswith("syntax is:")
			inCommandTable = inCommandTable or inUsage
			continue
		inCommandTable = False
		prose.append(row)
	flushProse()
	return units


def _translationPairedHelpLines(chinese, english):
	"""Pair help rows only when worker and original semantic units align exactly."""
	englishRows = _translationHelpSemanticLines(english)
	if not englishRows:
		return []
	chineseRows = [line.strip() for line in chinese.splitlines() if line.strip()]
	if len(chineseRows) != len(englishRows):
		return []
	return [chineseRow + " | " + englishRow for chineseRow, englishRow in zip(chineseRows, englishRows)]


def _translationCommandUsageLines(english):
	"""Keep a standalone Usage command table as one review row per command."""
	rows = [line.strip() for line in english.splitlines() if line.strip()]
	if len(rows) < 2 or rows[0].lower() != "usage:":
		return []
	root = None
	for row in rows[1:]:
		match = re.fullmatch(r"(.+?)\s+-\s+(.+)", row)
		if not match or not _isHelpUsageCommand(match.group(1).strip()):
			return []
		commandRoot = match.group(1).strip().split(None, 1)[0].lower()
		if root is None:
			root = commandRoot
		elif commandRoot != root:
			return []
	return rows


def _translationPairedCommandUsageLines(chinese, english):
	englishRows = _translationCommandUsageLines(english)
	if not englishRows:
		return []
	chineseRows = [line.strip() for line in chinese.splitlines() if line.strip()]
	if len(chineseRows) != len(englishRows):
		return []
	return [chineseRow + " | " + englishRow for chineseRow, englishRow in zip(chineseRows, englishRows)]


def _translationNewsSemanticLines(english):
	"""Restore stable rows for Alter Aeon's news report.

	The headline prose may be hard-wrapped by the MUD, while the remaining
	labels and area table already form semantic rows.  Join only that wrapped
	prose and preserve every fixed/news-table row.
	"""
	rows = [line.strip() for line in english.splitlines() if line.strip()]
	if len(rows) < 2 or rows[0].upper() != "ALTER AEON NEWS":
		return []
	output = [rows[0]]
	index = 1
	if rows[index].upper() == "TODAY'S HEADLINE:":
		output.append(rows[index])
		index += 1
	prose = []

	def flushProse():
		if prose:
			output.append(" ".join(prose))
			prose[:] = []

	def isFixedRow(row):
		return (
			row.startswith((
				"Alter Aeon was last booted:", "(Type 'changes'",
				"Got Their Freak On:", "Catch of the Day:",
				"Last Meteor Sighting:", "New and recently updated areas:",
			))
			or row == "Recent Archery Contest Winners:"
			or re.match(r"^.+?\s+won a jackpot!$", row, re.I)
			or re.match(r"^.+?\s+-\s+score\s+\d+\s+-\s+.+$", row, re.I)
			or re.match(r"^Date\s+Level\s+\[\s*X,\s*Y\]\s+Name\s+Creators$", row, re.I)
			or re.match(r"^[A-Z][a-z]{2}\s+\d{1,2}\s+\d{4}\s+(?:Lvl|Tot)\s+\d+\s+\[", row)
		)

	for row in rows[index:]:
		if isFixedRow(row):
			flushProse()
			output.append(row)
			continue
		prose.append(row)
		if re.search(r"[.!?][\"')\]]*$", row):
			flushProse()
	flushProse()
	return output


def _translationPairedNewsLines(chinese, english):
	englishRows = _translationNewsSemanticLines(english)
	if not englishRows:
		return []
	chineseRows = [line.strip() for line in chinese.splitlines() if line.strip()]
	if len(chineseRows) != len(englishRows):
		return []
	return [chineseRow + " | " + englishRow for chineseRow, englishRow in zip(chineseRows, englishRows)]


def _translationChangesSemanticLines(english):
	"""Restore one row per change-log header, author and complete update item."""
	rows = [line.strip() for line in english.splitlines() if line.strip()]
	if not rows or not re.match(r"^\[\d+\]\s+----\s+", rows[0]):
		return []
	output, prose = [], []

	def flushProse():
		if prose:
			output.append(" ".join(prose))
			prose[:] = []

	for row in rows:
		if re.match(r"^\[\d+\]\s+----\s+", row) or re.match(r"^From\s+.+?:$", row, re.I):
			flushProse()
			output.append(row)
			continue
		prose.append(row)
		if re.search(r"(?:[.!?][\"')\]]*|[.!?]\s+\([^)]+\))\s*$", row):
			flushProse()
	flushProse()
	return output


def _translationPairedChangesLines(chinese, english):
	englishRows = _translationChangesSemanticLines(english)
	if not englishRows:
		return []
	chineseRows = [line.strip() for line in chinese.splitlines() if line.strip()]
	if len(chineseRows) != len(englishRows):
		return []
	return [chineseRow + " | " + englishRow for chineseRow, englishRow in zip(chineseRows, englishRows)]


def _translationEnglishPresentationLines(english):
	"""Keep help fields and semantic paragraphs separate; rooms stay one line."""
	english = english.strip()
	if not english:
		return []
	rows = [line.strip() for line in english.splitlines() if line.strip()]
	isHelp = any(re.match(r"^(?:Showing page \d+\.|Keywords are:|Skill:|Spell:|Usage:)", row, re.I) for row in rows)
	if not isHelp:
		return [" ".join(english.split())]
	output, prose = [], []

	def flushProse():
		if prose:
			output.append(" ".join(prose))
			prose[:] = []

	for row in rows:
		field = re.match(
			r"^(?:Showing page \d+\.|Keywords are:|Skill:|Spell:|Usage:|"
			r"\(?(?:helpful|important|critical|useful)\)?\s+Requires:|Group:|Speed:)",
			row,
			re.I,
		)
		usageCommand = bool(output and output[-1].lower() == "usage:" and re.match(r"^[a-z][a-z -]*(?:\s+<[^>]+>)+$", row, re.I))
		if field or usageCommand:
			flushProse()
			output.append(row)
			continue
		prose.append(row)
		if re.search(r"[.!?]['\")\]]*$", row):
			flushProse()
	flushProse()
	return output


def _translationPresentationChineseStart(text):
	"""Find the first displayed Chinese line after one or more English lines."""
	position = 0
	for line in text.splitlines(keepends=True):
		content = line.rstrip("\r\n")
		if any(_isCJK(character) for character in content):
			return position
		position += len(line)
	return -1


def _isStructuredTranslationReview(english):
	"""Keep specialized multi-row presentation for skills and quest fields."""
	value = english.strip()
	if re.match(
		r"^(?:Quest Name|Magic Quest Name|Location|Area Level|Author|Editor|"
		r"Approximate Difficulty|Quest Summary|General Quest Info|"
		r"Previous Objective|Current Objective)(?:\s|:)",
		value,
		re.I,
	):
		return True
	if re.match(r"^You know the following skills:", value, re.I):
		return True
	return bool(re.search(r"\b\d{1,3}%\b", value) or re.search(r"(?:^|\s)--(?:\s|$)", value))


def _boundedReviewChunks(value, limit=600):
	"""Bound malformed legacy single rows so NVDA text ranges stay responsive."""
	value = (value or "").strip()
	chunks = []
	while len(value) > limit:
		window = value[:limit + 1]
		breaks = [match.end() for match in re.finditer(r"[。！？!?；;，,\]\)]\s*|\s+", window)]
		cut = max((point for point in breaks if point >= limit // 2), default=limit)
		chunks.append(value[:cut].strip())
		value = value[cut:].strip()
	if value:
		chunks.append(value)
	return chunks


def _boundedBilingualFallback(chinese, english):
	chineseChunks = _boundedReviewChunks(chinese)
	englishChunks = _boundedReviewChunks(english)
	count = max(len(chineseChunks), len(englishChunks))
	if count <= 1:
		return chinese + " | " + english
	rows = []
	for index in range(count):
		left = chineseChunks[index] if index < len(chineseChunks) else ""
		right = englishChunks[index] if index < len(englishChunks) else ""
		rows.append((left + " | " + right).strip())
	return "\n".join(rows)


def _translationReviewEnvelope(text):
	"""Return versioned navigation metadata and visible review text."""
	metadata = {"kind": "", "edge": "none"}
	match = re.match(
		r"^\x1eTMREVIEW2:id=(\d+);pos=(\d+);count=(\d+);rev=(\d+);"
		r"edge=(oldest|latest|none);kind=(quest|job|skills)?\x1e",
		text or "",
	)
	if match:
		metadata.update({
			"id": int(match.group(1)),
			"pos": int(match.group(2)),
			"count": int(match.group(3)),
			"rev": int(match.group(4)),
			"edge": match.group(5),
			"kind": match.group(6) or "",
		})
		return metadata, text[match.end():]
	legacy = re.match(r"^\x1eTMREVIEW:(quest|job|skills)\x1e", text or "")
	if legacy:
		metadata["kind"] = legacy.group(1)
		return metadata, text[legacy.end():]
	return metadata, text


def _translationReviewMetadata(text):
	"""Compatibility helper returning category and visible review text."""
	metadata, visible = _translationReviewEnvelope(text)
	return metadata["kind"], visible


def _translationReviewPresentation(text):
	"""Show every translated history row as stable same-line bilingual text."""
	if not text:
		return ""
	reviewKind, text = _translationReviewMetadata(text)
	divider = text.find("|")
	if divider < 0:
		return text
	chinese = text[:divider]
	english = text[divider + 1:]
	chineseLine = re.sub(r"\s+", " ", chinese).strip()
	englishLine = re.sub(r"\s+", " ", english).strip()
	if chineseLine and englishLine:
		pairedTaskList = _translationPairedTaskListLines(chinese, english)
		if pairedTaskList:
			return "\n".join(pairedTaskList)
		pairedSales = _translationPairedSalesLines(chinese, english)
		if pairedSales:
			return "\n".join(pairedSales)
		pairedSyntax = _translationPairedSyntaxLines(chinese, english)
		if pairedSyntax:
			return "\n".join(pairedSyntax)
		pairedCommandUsage = _translationPairedCommandUsageLines(chinese, english)
		if pairedCommandUsage:
			return "\n".join(pairedCommandUsage)
		pairedNews = _translationPairedNewsLines(chinese, english)
		if pairedNews:
			return "\n".join(pairedNews)
		pairedChanges = _translationPairedChangesLines(chinese, english)
		if pairedChanges:
			return "\n".join(pairedChanges)
		pairedHelp = _translationPairedHelpLines(chinese, english)
		if pairedHelp:
			return "\n".join(pairedHelp)
		pairedDialogue = _translationPairedDialogueLines(chinese, english)
		if pairedDialogue:
			return "\n".join(pairedDialogue)
		pairedMonsterLore = _translationPairedMonsterLoreLines(chinese, english)
		if pairedMonsterLore:
			return "\n".join(pairedMonsterLore)
		pairedRoom = _translationPairedRoomLines(chinese, english)
		if pairedRoom:
			return "\n".join(pairedRoom)
		englishRows = [line.strip() for line in english.splitlines() if line.strip()]
		# A room that failed exact movement/title/prose alignment must stay intact;
		# generic sentence pairing could otherwise attach its title to prose.
		if _englishRoomTitleIndex(englishRows) < 0:
			pairedProse = _translationPairedProseLines(chinese, english)
			if pairedProse:
				return "\n".join(pairedProse)
		return _boundedBilingualFallback(chineseLine, englishLine)
	chineseLines = _translationChinesePresentationLines(chinese, english)
	keys = _translationEnglishKeys(english)
	englishLines = [line.strip() for line in english.splitlines() if line.strip()]
	roomTitleIndex = _englishRoomTitleIndex(englishLines)
	roomTitle = englishLines[roomTitleIndex] if roomTitleIndex >= 0 else ""
	if roomTitle and chineseLines and roomTitle in keys:
		titleType = roomTitle.lower().split()[-1]
		suffixes = _roomTitleChineseSuffixes.get(titleType, ())
		chineseTitleIndex = next(
			(index for index, line in enumerate(chineseLines)
			 if not re.search(r"[。！？!?]$", line) and (not suffixes or line.endswith(suffixes))),
			0,
		)
		chineseLines[chineseTitleIndex] += "〔" + roomTitle + "〕"
		keys = [key for key in keys if key != roomTitle]
	if keys:
		chineseLines.append("〔" + "；".join(keys) + "〕")
	return "\n".join(chineseLines)


def _translationOriginalEnglish(text):
	"""Return the complete English half of the current bilingual entry."""
	if not text:
		return ""
	unusedKind, text = _translationReviewMetadata(text)
	divider = text.find("|")
	if divider < 0:
		return ""
	return text[divider + 1:].strip()


def _translationPresentationSegments(text):
	"""Return Chinese clauses and English words exposed by virtual review."""
	if not text:
		return []
	chineseStart = _translationPresentationChineseStart(text)
	if chineseStart < 0:
		return [(match.start(), match.end()) for match in re.finditer(r"[A-Za-z0-9][A-Za-z0-9'-]*", text)]
	segments = []
	position = chineseStart
	for line in text[position:].splitlines(keepends=True):
		content = line.rstrip("\r\n")
		divider = content.find(" | ")
		if divider >= 0:
			chinesePart = content[:divider]
			clauseStart = 0
			for boundary in re.finditer(r"[，,。！？!?；;：:]", chinesePart):
				end = boundary.end()
				left = clauseStart
				while left < end and chinesePart[left].isspace():
					left += 1
				if left < end:
					segments.append((position + left, position + end))
				clauseStart = end
			left = clauseStart
			while left < len(chinesePart) and chinesePart[left].isspace():
				left += 1
			if left < len(chinesePart):
				segments.append((position + left, position + len(chinesePart.rstrip())))
			for word in re.finditer(r"[A-Za-z0-9][A-Za-z0-9'-]*", content[divider + 3:]):
				start = position + divider + 3 + word.start()
				segments.append((start, start + len(word.group(0))))
			position += len(line)
			continue
		# English exposed inside 〔...〕 follows NVDA's documented word
		# navigation: numpad4/6 moves one word at a time. Chinese prose uses
		# clauses because NVDA has no useful space-delimited words there.
		brackets = list(re.finditer(r"〔([^〕]*)〕", content))
		cursor = 0
		for bracket in brackets + [None]:
			regionEnd = bracket.start() if bracket else len(content)
			region = content[cursor:regionEnd]
			regionStart = position + cursor
			clauseStart = 0
			for boundary in re.finditer(r"[，,。！？!?；;：:]", region):
				end = boundary.end()
				left = clauseStart
				while left < end and region[left].isspace():
					left += 1
				if left < end and any(_isCJK(character) for character in region[left:end]):
					segments.append((regionStart + left, regionStart + end))
				clauseStart = end
			left = clauseStart
			while left < len(region) and region[left].isspace():
				left += 1
			if left < len(region) and any(_isCJK(character) for character in region[left:]):
				segments.append((regionStart + left, regionStart + len(region.rstrip())))
			if not bracket:
				break
			for word in re.finditer(r"[A-Za-z0-9][A-Za-z0-9'-]*", bracket.group(1)):
				start = position + bracket.start(1) + word.start()
				segments.append((start, start + len(word.group(0))))
			cursor = bracket.end()
		position += len(line)
	return segments


def _translationPresentationInitialOffset(text):
	"""Start review at the beginning of the first displayed Chinese segment."""
	chineseStart = _translationPresentationChineseStart(text) if text else -1
	if chineseStart < 0:
		return 0
	while chineseStart < len(text) and text[chineseStart].isspace():
		chineseStart += 1
	return chineseStart


def _translationPresentationLineRanges(text):
	"""Return each non-empty displayed line as an independent review range."""
	ranges = []
	position = 0
	for line in text.splitlines(keepends=True):
		content = line.rstrip("\r\n")
		start = len(content) - len(content.lstrip())
		end = len(content.rstrip())
		if end > start:
			ranges.append((position + start, position + end))
		position += len(line)
	return ranges


def _translationPresentationBottomChineseRange(text):
	"""Return the bottom Chinese line selected for initial history feedback."""
	start = _translationPresentationInitialOffset(text)
	if not text or start >= len(text):
		return 0, 0
	end = text.find("\n", start)
	if end < 0:
		end = len(text)
	return start, end


def _translationPresentationChineseText(text):
	"""Return every displayed Chinese line, excluding all English lines."""
	chineseStart = _translationPresentationChineseStart(text) if text else -1
	if chineseStart < 0:
		return text.strip() if text else ""
	return text[chineseStart:].strip()


class TranslationReviewTextInfo(NVDAObjectTextInfo):
	def _getWordOffsets(self, offset):
		offsets = _translationSentenceOffsets(self._getStoryText(), offset)
		return offsets if offsets else super()._getWordOffsets(offset)


def _translationReviewIsActive():
	"""Fail closed: any missing, malformed, or stale state restores NVDA review."""
	try:
		with open(REVIEW_STATE_FILE, "r", encoding="utf-8-sig") as state:
			heartbeat = state.readline().strip()
		if not heartbeat or not os.path.isfile(heartbeat):
			return False
		return time.time() - os.path.getmtime(heartbeat) <= 6.0
	except (OSError, UnicodeError):
		return False


class TranslationReviewObject(NVDAObject):
	"""Read-only virtual text used by NVDA's native review commands."""

	TextInfo = TranslationReviewTextInfo

	def __init__(self, text, parent, processID):
		self._reviewText = text
		self._reviewParent = parent
		self._reviewProcessID = processID
		super().__init__()

	def _get_basicText(self):
		return self._reviewText

	def _get_name(self):
		return "Translation Mode history"

	def _get_role(self):
		return controlTypes.Role.DOCUMENT

	def _get_processID(self):
		return self._reviewProcessID

	def _get_parent(self):
		return self._reviewParent

	def _get_location(self):
		try:
			return self._reviewParent.location
		except Exception:
			return None


def _translationReviewInfoAtOffset(obj, offset):
	"""Create a collapsed virtual TextInfo without walking through preceding text.

	NVDAObjectTextInfo only accepts NVDA position constants when it is created;
	passing an ``(offset, offset)`` tuple silently breaks review navigation on NVDA
	2026.2.  Calling ``move`` from the first character is valid but can make
	Uniscribe scan a very large entry on NVDA's main thread.  Initialising the
	valid object first and then setting its native offsets avoids both failures.
	"""
	info = obj.makeTextInfo(textInfos.POSITION_FIRST)
	target = max(0, min(len(obj.basicText), int(offset)))
	info._startOffset = target
	info._endOffset = target
	return info


def _readTranslationReviewEntry():
	if not _translationReviewIsActive():
		return None
	try:
		with open(REVIEW_ENTRY_FILE, "r", encoding="utf-8-sig") as entry:
			text = entry.read()
			return text if text else None
	except (OSError, UnicodeError):
		return None


def _reviewEntrySignature():
	"""Identify a completed response, including same-size repeated entries."""
	try:
		with open(REVIEW_ENTRY_FILE, "r", encoding="utf-8-sig") as entry:
			metadata, unusedText = _translationReviewEnvelope(entry.read())
		if "rev" in metadata:
			return ("v2", metadata["rev"], metadata["id"], metadata["pos"], metadata["count"])
		stat = os.stat(REVIEW_ENTRY_FILE)
		return ("legacy", stat.st_mtime_ns, stat.st_size)
	except (OSError, UnicodeError):
		return None


def _translationOrNative(gesture, translationGesture, nativeScript, afterTranslation=None):
	global _reviewRequestGeneration
	if _translationReviewIsActive():
		before = _reviewEntrySignature()
		_reviewRequestGeneration += 1
		generation = _reviewRequestGeneration
		started = time.monotonic()
		_translationDiagnostic(
			"request_sent", generation=generation, command=translationGesture,
			before_signature=repr(before),
		)
		KeyboardInputGesture.fromName(translationGesture).send()
		if afterTranslation:
			def poll(attempt=0, changed=None):
				if generation != _reviewRequestGeneration:
					_translationDiagnostic(
						"request_superseded", generation=generation,
						new_generation=_reviewRequestGeneration,
						elapsed_ms=round((time.monotonic() - started) * 1000, 1),
					)
					return
				current = _reviewEntrySignature()
				if current is not None and current != before:
					if changed == current:
						_translationDiagnostic(
							"response_ready", generation=generation,
							elapsed_ms=round((time.monotonic() - started) * 1000, 1),
							response_signature=repr(current), attempts=attempt,
						)
						afterTranslation()
						return
					# Require one 10 ms stable observation. Rapid repeated keys can
					# replace the file again; in that case only the newest entry wins.
					core.callLater(10, lambda: poll(attempt + 1, current))
					return
				if attempt >= 80:
					# MUSHclient rewrites the review entry even at a real history
					# boundary.  If no rewrite arrived, the request has not completed;
					# inspecting the old text here would falsely announce "oldest" or
					# "latest" and make a later completed request look like a jump.
					_translationDiagnostic(
						"request_timeout", generation=generation,
						elapsed_ms=round((time.monotonic() - started) * 1000, 1),
						before_signature=repr(before), attempts=attempt,
					)
					ui.message("翻譯紀錄尚未更新，請再按一次。")
					return
				core.callLater(10, lambda: poll(attempt + 1, changed))
			core.callLater(0, poll)
	else:
		nativeScript(gesture)


class Input(Window):
	_output = None

	def event_gainFocus(self):
		super().event_gainFocus()
		self.setNavigator()

	def event_caret(self):
		super().event_caret()
		self.setNavigator()

	def setNavigator(self):
		currentNavigator = api.getNavigatorObject()
		# Typing moves the command edit's caret and calls this method for every
		# character.  Do not throw away Translation Mode's virtual review cursor:
		# the player may be copying a long English name one character at a time
		# with numpad1/3 while composing a command.  Outside that virtual document,
		# retain Mush-Z's original behaviour of following the English output.
		if _translationReviewIsActive() and isinstance(currentNavigator, TranslationReviewObject):
			return
		if self._output and currentNavigator == self._output:
			return
		self._output = None
		try:
			output = self.parent.parent.parent.parent.parent.next.firstChild.next.next.firstChild.firstChild
		except Exception:
			return
		if output.windowControlID != 59648:
			return
		api.setNavigatorObject(output)
		self._output = output


class AppModule(appModuleHandler.AppModule):
	_translationReviewObject = None
	_translationSentenceIndex = -1

	def _translationReviewCurrentOffset(self):
		"""Return NVDA's real review offset inside our virtual document."""
		if self._translationReviewObject is None:
			return None
		try:
			info = api.getReviewPosition()
			if getattr(info, "obj", None) is not self._translationReviewObject:
				return None
			offset = int(getattr(info, "_startOffset"))
			return max(0, min(len(self._translationReviewObject.basicText), offset))
		except (AttributeError, TypeError, ValueError):
			return None

	def _translationSegmentIndexAtOffset(self, segments, offset):
		"""Map the real review cursor to the sentence/word segment it occupies."""
		if offset is None or not segments:
			return None
		for index, (start, end) in enumerate(segments):
			if start <= offset < end:
				return index
		# At whitespace or the exact line end, use the nearest segment on that
		# line. This keeps Shift+numpad1/3 compatible with numpad4/6.
		text = self._translationReviewObject.basicText
		lineStart = text.rfind("\n", 0, offset) + 1
		lineEnd = text.find("\n", offset)
		if lineEnd < 0:
			lineEnd = len(text)
		lineIndexes = [
			index for index, (start, end) in enumerate(segments)
			if start >= lineStart and end <= lineEnd
		]
		if not lineIndexes:
			return None
		return min(
			lineIndexes,
			key=lambda index: min(
				abs(offset - segments[index][0]),
				abs(offset - segments[index][1]),
			),
		)

	def _syncTranslationReviewPosition(self, announce=False, atEnd=False):
		text = _readTranslationReviewEntry()
		if not text:
			return
		try:
			presentation = _translationReviewPresentation(text)
			parent = api.getFocusObject()
			processID = parent.processID
			obj = TranslationReviewObject(
				chooseBestAPI=False,
				text=presentation,
				parent=parent,
				processID=processID,
			)
			lineRanges = _translationPresentationLineRanges(presentation)
			targetLine = lineRanges[-1] if atEnd and lineRanges else (lineRanges[0] if lineRanges else (0, 0))
			# Avoid TextInfo.move here: long entries can make NVDA/Uniscribe scan
			# every preceding character on the main thread.
			info = _translationReviewInfoAtOffset(obj, targetLine[0])
			if api.setReviewPosition(info):
				self._translationReviewObject = obj
				self._translationSentenceIndex = -1
				if announce:
					if lineRanges:
						start, end = targetLine
						ui.message(presentation[start:end])
		except Exception:
			# A virtual review failure must never interfere with gameplay or with
			# the existing English output navigator.
			return

	def _moveTranslationSentence(self, gesture, direction, nativeScript):
		"""Move 4/6 through Chinese sentences in the virtual review document."""
		if not _translationReviewIsActive():
			nativeScript(gesture)
			return
		text = _readTranslationReviewEntry()
		if not text:
			nativeScript(gesture)
			return
		presentation = _translationReviewPresentation(text)
		if self._translationReviewObject is None or self._translationReviewObject.basicText != presentation:
			self._syncTranslationReviewPosition()
		segments = _translationPresentationSegments(presentation)
		if not segments or self._translationReviewObject is None:
			nativeScript(gesture)
			return
		actualIndex = self._translationSegmentIndexAtOffset(
			segments,
			self._translationReviewCurrentOffset(),
		)
		if actualIndex is not None:
			self._translationSentenceIndex = actualIndex
		if self._translationSentenceIndex < 0:
			# Both directions start on Chinese so English can never replace the
			# first bilingual review announcement.
			self._translationSentenceIndex = 0
		else:
			self._translationSentenceIndex = max(
				0,
				min(len(segments) - 1, self._translationSentenceIndex + direction),
			)
		start, end = segments[self._translationSentenceIndex]
		info = _translationReviewInfoAtOffset(self._translationReviewObject, start)
		if api.setReviewPosition(info):
			# Speak the selected Chinese sentence or English word explicitly. Do
			# not route this through
			# NVDA's current-word command: some NVDA versions resolve the virtual
			# TextInfo at the collapsed caret and announce only one character.
			ui.message(presentation[start:end])

	def _moveTranslationLineEdge(self, gesture, toEnd):
		"""Apply native line-edge semantics and keep the 4/6 index synchronized."""
		if not _translationReviewIsActive():
			native = (
				globalCommands.commands.script_review_endOfLine
				if toEnd else globalCommands.commands.script_review_startOfLine
			)
			native(gesture)
			return
		text = _readTranslationReviewEntry()
		if not text:
			return
		presentation = _translationReviewPresentation(text)
		if self._translationReviewObject is None or self._translationReviewObject.basicText != presentation:
			self._syncTranslationReviewPosition()
		segments = _translationPresentationSegments(presentation)
		if not segments or self._translationReviewObject is None:
			return
		offset = self._translationReviewCurrentOffset()
		if offset is None:
			offset = _translationPresentationInitialOffset(presentation)
		lineStart = presentation.rfind("\n", 0, offset) + 1
		lineEnd = presentation.find("\n", offset)
		if lineEnd < 0:
			lineEnd = len(presentation)
		lineIndexes = [
			i for i, (start, end) in enumerate(segments)
			if start >= lineStart and end <= lineEnd
		]
		if lineIndexes:
			self._translationSentenceIndex = lineIndexes[-1] if toEnd else lineIndexes[0]
		target = max(lineStart, lineEnd - 1) if toEnd else lineStart
		info = _translationReviewInfoAtOffset(self._translationReviewObject, target)
		api.setReviewPosition(info)

	def _moveTranslationHistoryLine(self, gesture, direction, translationGesture, nativeScript):
		"""Move within one entry first; cross history only at its line boundary."""
		if not _translationReviewIsActive():
			nativeScript(gesture)
			return
		text = _readTranslationReviewEntry()
		if not text:
			nativeScript(gesture)
			return
		presentation = _translationReviewPresentation(text)
		metadata, unusedVisible = _translationReviewEnvelope(text)
		if self._translationReviewObject is None or self._translationReviewObject.basicText != presentation:
			self._syncTranslationReviewPosition()
		lineRanges = _translationPresentationLineRanges(presentation)
		offset = self._translationReviewCurrentOffset()
		if lineRanges and offset is not None and self._translationReviewObject is not None:
			current = next(
				(index for index, (start, end) in enumerate(lineRanges) if start <= offset <= end),
				min(range(len(lineRanges)), key=lambda index: abs(offset - lineRanges[index][0])),
			)
			target = current + direction
			if 0 <= target < len(lineRanges):
				start, end = lineRanges[target]
				info = _translationReviewInfoAtOffset(self._translationReviewObject, start)
				if api.setReviewPosition(info):
					self._translationSentenceIndex = -1
					_translationDiagnostic(
						"line_move", direction=direction, entry_id=metadata.get("id"),
						position=metadata.get("pos"), count=metadata.get("count"),
						from_line=current, to_line=target, line_count=len(lineRanges),
					)
					ui.message(presentation[start:end])
				return
		_translationDiagnostic(
			"history_cross_request", direction=direction, entry_id=metadata.get("id"),
			position=metadata.get("pos"), count=metadata.get("count"),
			line_count=len(lineRanges),
		)
		def syncChangedHistoryEntry():
			updated = _readTranslationReviewEntry()
			metadata, unusedVisible = _translationReviewEnvelope(updated or "")
			if metadata.get("edge") == "latest":
				_translationDiagnostic(
					"history_edge", edge="latest", entry_id=metadata.get("id"),
					position=metadata.get("pos"), count=metadata.get("count"),
				)
				ui.message("已到最新一筆翻譯紀錄。")
				return
			if metadata.get("edge") == "oldest":
				_translationDiagnostic(
					"history_edge", edge="oldest", entry_id=metadata.get("id"),
					position=metadata.get("pos"), count=metadata.get("count"),
				)
				ui.message("已到最舊一筆翻譯紀錄。")
				return
			_translationDiagnostic(
				"history_entry_loaded", direction=direction, entry_id=metadata.get("id"),
				position=metadata.get("pos"), count=metadata.get("count"),
			)
			self._syncTranslationReviewPosition(True, atEnd=direction < 0)

		_translationOrNative(
			gesture,
			translationGesture,
			nativeScript,
			syncChangedHistoryEntry,
		)

	def chooseNVDAObjectOverlayClasses(self, obj, clsList):
		if (
			getattr(obj, "windowClassName", None) == "Edit"
			and getattr(obj, "windowControlID", None) == 59664
			and getattr(obj, "IAccessibleRole", None) == oleacc.ROLE_SYSTEM_TEXT
		):
			clsList.insert(0, Input)

	@scriptHandler.script(
		description="Previous Chinese segment, or NVDA previous review word",
		gesture="kb:numpad4",
	)
	def script_translationSentencePrevious(self, gesture):
		self._moveTranslationSentence(
			gesture,
			-1,
			globalCommands.commands.script_review_previousWord,
		)

	@scriptHandler.script(
		description="Next Chinese segment, or NVDA next review word",
		gesture="kb:numpad6",
	)
	def script_translationSentenceNext(self, gesture):
		self._moveTranslationSentence(
			gesture,
			1,
			globalCommands.commands.script_review_nextWord,
		)

	@scriptHandler.script(
		description="Start of current Translation Mode review line",
		gesture="kb:shift+numpad1",
	)
	def script_translationReviewStartOfLine(self, gesture):
		self._moveTranslationLineEdge(gesture, False)

	@scriptHandler.script(
		description="End of current Translation Mode review line",
		gesture="kb:shift+numpad3",
	)
	def script_translationReviewEndOfLine(self, gesture):
		self._moveTranslationLineEdge(gesture, True)

	@scriptHandler.script(
		description="Previous Translation Mode history entry, or NVDA previous review line",
		gesture="kb:numpad7",
	)
	def script_translationHistoryPrevious(self, gesture):
		self._moveTranslationHistoryLine(
			gesture,
			-1,
			"control+alt+shift+pageUp",
			globalCommands.commands.script_review_previousLine,
		)

	@scriptHandler.script(
		description="Next Translation Mode history entry, or NVDA next review line",
		gesture="kb:numpad9",
	)
	def script_translationHistoryNext(self, gesture):
		self._moveTranslationHistoryLine(
			gesture,
			1,
			"control+alt+shift+pageDown",
			globalCommands.commands.script_review_nextLine,
		)

	@scriptHandler.script(
		description="First Translation Mode history entry, or NVDA top review line",
		gesture="kb:shift+numpad7",
	)
	def script_translationHistoryTop(self, gesture):
		_translationOrNative(
			gesture,
			"control+alt+shift+home",
			globalCommands.commands.script_review_top,
			lambda: self._syncTranslationReviewPosition(True),
		)

	@scriptHandler.script(
		description="Last Translation Mode history entry, or NVDA bottom review line",
		gesture="kb:shift+numpad9",
	)
	def script_translationHistoryBottom(self, gesture):
		_translationOrNative(
			gesture,
			"control+alt+shift+end",
			globalCommands.commands.script_review_bottom,
			lambda: self._syncTranslationReviewPosition(True, atEnd=True),
		)
