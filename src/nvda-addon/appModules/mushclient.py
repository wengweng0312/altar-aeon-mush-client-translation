# -*- coding: utf-8 -*-
# Merged Mush Client accessibility app module and optional Translation Mode review navigation.

import os
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
_reviewRequestGeneration = 0

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
	"""Find a room title even when a status line precedes the room block."""
	for index, row in enumerate(rows[:-1]):
		if not row or len(row) > 80 or re.search(r"[.!?:;]$", row):
			continue
		if re.match(r"^(?:you|your|there|exits?|mobs?|level|experience)\b", row, re.I):
			continue
		nextRow = rows[index + 1]
		# A title is normally followed by prose substantially longer than itself.
		# This rejects an unpunctuated status line followed by the actual title.
		if len(nextRow) >= len(row) + 8 or re.search(r"[.!?]$", nextRow):
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
	if re.match(r"^[^\r\n]+?\s+(?:says|asks),\s*['\"]", english.strip(), re.I) or re.match(
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


def _translationReviewMetadata(text):
	"""Remove Translation Mode's private category marker from review text."""
	match = re.match(r"^\x1eTMREVIEW:(quest|job|skills)\x1e", text or "")
	if not match:
		return "", text
	return match.group(1), text[match.end():]


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
		return chineseLine + " | " + englishLine
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
	"""Identify an atomically replaced review entry without reading its text."""
	try:
		stat = os.stat(REVIEW_ENTRY_FILE)
		return stat.st_mtime_ns, stat.st_size
	except OSError:
		return None


def _translationOrNative(gesture, translationGesture, nativeScript, afterTranslation=None):
	global _reviewRequestGeneration
	if _translationReviewIsActive():
		before = _reviewEntrySignature()
		_reviewRequestGeneration += 1
		generation = _reviewRequestGeneration
		KeyboardInputGesture.fromName(translationGesture).send()
		if afterTranslation:
			def poll(attempt=0, changed=None):
				if generation != _reviewRequestGeneration:
					return
				current = _reviewEntrySignature()
				if current is not None and current != before:
					if changed == current:
						afterTranslation()
						return
					# Require one 5 ms stable observation. Rapid repeated keys can
					# replace the file again; in that case only the newest entry wins.
					core.callLater(5, lambda: poll(attempt + 1, current))
					return
				if attempt >= 24:
					# Preserve the old safe fallback on unusually slow filesystems.
					afterTranslation()
					return
				core.callLater(5, lambda: poll(attempt + 1, changed))
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
		if self._output and api.getNavigatorObject() == self._output:
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
			info = obj.makeTextInfo(textInfos.POSITION_FIRST)
			info.move(textInfos.UNIT_CHARACTER, targetLine[0])
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
		info = self._translationReviewObject.makeTextInfo(textInfos.POSITION_FIRST)
		info.move(textInfos.UNIT_CHARACTER, start)
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
		info = self._translationReviewObject.makeTextInfo(textInfos.POSITION_FIRST)
		info.move(textInfos.UNIT_CHARACTER, target)
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
				info = self._translationReviewObject.makeTextInfo(textInfos.POSITION_FIRST)
				info.move(textInfos.UNIT_CHARACTER, start)
				if api.setReviewPosition(info):
					self._translationSentenceIndex = -1
					ui.message(presentation[start:end])
				return
		_translationOrNative(
			gesture,
			translationGesture,
			nativeScript,
			lambda: self._syncTranslationReviewPosition(True, atEnd=direction < 0),
		)

	def chooseNVDAObjectOverlayClasses(self, obj, clsList):
		if (
			obj.windowClassName == "Edit"
			and obj.windowControlID == 59664
			and obj.IAccessibleRole == oleacc.ROLE_SYSTEM_TEXT
		):
			clsList.insert(0, Input)

	@scriptHandler.script(
		description="Speak the English original; press twice to copy it",
		gesture="kb:control+shift+y",
	)
	def script_translationOriginalEnglish(self, gesture):
		if not _translationReviewIsActive():
			ui.message("翻譯模式未開啟。")
			return
		if scriptHandler.getLastScriptRepeatCount() > 0:
			english = getattr(self, "_translationOriginalForRepeat", "")
			if not english:
				english = _translationOriginalEnglish(_readTranslationReviewEntry())
			if not english:
				ui.message("這一筆沒有英文原文。")
				return
			try:
				api.copyToClip(english, notify=False)
			except TypeError:
				api.copyToClip(english)
			ui.message("已複製英文原文。")
			return
		english = _translationOriginalEnglish(_readTranslationReviewEntry())
		if not english:
			ui.message("這一筆沒有英文原文。")
			return
		self._translationOriginalForRepeat = english
		_translationOrNative(
			gesture,
			"control+alt+shift+y",
			lambda ignoredGesture: ui.message(english),
			lambda: self._syncTranslationReviewPosition(True),
		)

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
			lambda: self._syncTranslationReviewPosition(True),
		)
