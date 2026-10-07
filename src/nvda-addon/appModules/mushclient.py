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


def _isCJK(character):
	if not character:
		return False
	code = ord(character)
	return (
		0x3400 <= code <= 0x4DBF
		or 0x4E00 <= code <= 0x9FFF
		or 0xF900 <= code <= 0xFAFF
	)


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
	# Room output commonly has a short, punctuation-free English title on its
	# own first line. Translation may join its Chinese title to the first
	# sentence with one space, so split that title only in this presentation.
	if (
		len(englishLines) >= 2
		and len(englishLines[0]) <= 80
		and englishLines[0][-1:] not in ".!?:;"
	):
		firstSpace = re.search(r"\s+", chinese)
		firstTerminator = re.search(r"[。！？!?\r\n]", chinese)
		if firstSpace and (not firstTerminator or firstSpace.start() < firstTerminator.start()):
			title = chinese[:firstSpace.start()].strip()
			remainder = chinese[firstSpace.end():].strip()
			if 1 < len(title) <= 40 and any(_isCJK(character) for character in title) and any(
				_isCJK(character) for character in remainder
			):
				lines.append(title)
				chinese = remainder
	start = 0
	for match in re.finditer(r"[。！？!?\r\n]", chinese):
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


def _translationReviewPresentation(text):
	"""Place English above line-broken Chinese for bottom-up review."""
	if not text:
		return ""
	divider = text.find("|")
	if divider < 0:
		return text
	chinese = text[:divider]
	english = text[divider + 1:]
	englishLines = _translationEnglishPresentationLines(english)
	chineseLines = _translationChinesePresentationLines(chinese, english)
	parts = englishLines + chineseLines
	return "\n".join(parts)


def _translationPresentationSegments(text):
	"""Return Chinese lines first, followed by words from all English lines."""
	if not text:
		return []
	chineseStart = _translationPresentationChineseStart(text)
	if chineseStart < 0:
		return [(match.start(), match.end()) for match in re.finditer(r"\S+", text)]
	segments = []
	position = chineseStart
	for line in text[position:].splitlines(keepends=True):
		content = line.rstrip("\r\n")
		leading = len(content) - len(content.lstrip())
		trailing = len(content.rstrip())
		if trailing > leading:
			segments.append((position + leading, position + trailing))
		position += len(line)
	for match in re.finditer(r"\S+", text[:chineseStart]):
		segments.append((match.start(), match.end()))
	return segments


def _translationPresentationInitialOffset(text):
	"""Start review at the bottom Chinese line, matching bottom-up reading."""
	chineseStart = _translationPresentationChineseStart(text) if text else -1
	if chineseStart < 0:
		return 0
	position = chineseStart
	last = position
	for line in text[position:].splitlines(keepends=True):
		if line.strip():
			last = position + len(line) - len(line.lstrip())
		position += len(line)
	return last


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

	def _syncTranslationReviewPosition(self, announce=False):
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
			info = obj.makeTextInfo(textInfos.POSITION_FIRST)
			info.move(textInfos.UNIT_CHARACTER, _translationPresentationInitialOffset(presentation))
			if api.setReviewPosition(info):
				self._translationReviewObject = obj
				self._translationSentenceIndex = -1
				if announce:
					chinese = _translationPresentationChineseText(presentation)
					if chinese:
						ui.message(chinese)
		except Exception:
			# A virtual review failure must never interfere with gameplay or with
			# the existing English output navigator.
			return

	def _moveTranslationSentence(self, gesture, direction, nativeScript):
		"""Move 4/6 through Chinese sentences, then English words."""
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

	def chooseNVDAObjectOverlayClasses(self, obj, clsList):
		if (
			obj.windowClassName == "Edit"
			and obj.windowControlID == 59664
			and obj.IAccessibleRole == oleacc.ROLE_SYSTEM_TEXT
		):
			clsList.insert(0, Input)

	@scriptHandler.script(
		description="Previous bilingual segment, or NVDA previous review word",
		gesture="kb:numpad4",
	)
	def script_translationSentencePrevious(self, gesture):
		self._moveTranslationSentence(
			gesture,
			-1,
			globalCommands.commands.script_review_previousWord,
		)

	@scriptHandler.script(
		description="Next bilingual segment, or NVDA next review word",
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
		_translationOrNative(
			gesture,
			"control+alt+shift+pageUp",
			globalCommands.commands.script_review_previousLine,
			lambda: self._syncTranslationReviewPosition(True),
		)

	@scriptHandler.script(
		description="Next Translation Mode history entry, or NVDA next review line",
		gesture="kb:numpad9",
	)
	def script_translationHistoryNext(self, gesture):
		_translationOrNative(
			gesture,
			"control+alt+shift+pageDown",
			globalCommands.commands.script_review_nextLine,
			lambda: self._syncTranslationReviewPosition(True),
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
