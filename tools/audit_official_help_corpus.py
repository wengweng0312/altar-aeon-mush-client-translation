"""Download and structurally audit the public Alter Aeon help corpus.

This is intentionally an analysis-only tool.  It never changes production
source, translation caches, or player configuration.
"""

from __future__ import annotations

import hashlib
import html
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"
OUTPUT_ROOT = ROOT / "analysis/help-corpus-audit"
CACHE_DIR = OUTPUT_ROOT / "download-cache"
LATEST_REPORT = OUTPUT_ROOT / "HELP_CORPUS_AUDIT_REPORT.md"
LATEST_POINTER = OUTPUT_ROOT / "latest_run.txt"
HELP_INDEX = "https://alteraeon.com:8081/help"
DELAY_SECONDS = 0.40
USER_AGENT = "Mush-Z-Translation-Help-Audit/1.0 (low-rate public help audit)"


def progress(message: str) -> None:
    print(message, flush=True)


def cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return CACHE_DIR / (digest + ".html")


def fetch(url: str, label: str) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(url)
    if path.is_file():
        progress("[使用快取] %s" % label)
        return path.read_text(encoding="utf-8", errors="replace")
    # The portable runtime does not ship a Windows CA bundle.  curl.exe is
    # included with supported Windows versions and uses the OS trust store,
    # so use it first rather than weakening TLS verification.
    last_error = None
    for attempt in range(1, 4):
        try:
            completed = subprocess.run(
                ["curl.exe", "--fail", "--silent", "--show-error", "--location",
                 "--max-time", "30", "--user-agent", USER_AGENT, url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if completed.returncode:
                raise RuntimeError(completed.stderr.decode("utf-8", errors="replace").strip())
            payload = completed.stdout.decode("utf-8", errors="replace")
            path.write_text(payload, encoding="utf-8")
            progress("[已下載（Windows 憑證）] %s" % label)
            time.sleep(DELAY_SECONDS)
            return payload
        except (OSError, urllib.error.URLError) as error:
            last_error = error
            progress("[重試 %d/3] %s：%s" % (attempt, label, error))
            time.sleep(2.0 * attempt)
    raise RuntimeError("download failed for %s: %s" % (url, last_error))


def hrefs(document: str, base: str) -> list[str]:
    values = re.findall(r"href\s*=\s*['\"]([^'\"]+)['\"]", document, re.I)
    return sorted({urllib.parse.urljoin(base, html.unescape(value)) for value in values})


def extract_help_text(document: str) -> str:
    match = re.search(r"<pre[^>]*>\s*<tt[^>]*>(.*?)</tt>\s*</pre>", document, re.I | re.S)
    if not match:
        return ""
    value = match.group(1)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in value.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def load_worker():
    spec = importlib.util.spec_from_file_location("official_help_audit_worker", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def trace_sources() -> list[dict[str, str]]:
    candidates = [
        Path(r"D:\altar aeon\Mush-Z\worlds\plugins\translation_bridge\lmt_translation_trace.log"),
        Path(r"P:\altar log\lmt_translation_trace.log"),
    ]
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in candidates:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(raw)
            except ValueError:
                continue
            source = str(record.get("source", ""))
            if not source.lstrip().startswith("Keywords are:") or source in seen:
                continue
            seen.add(source)
            found.append({"url": str(path), "source": source, "origin": "trace"})
    return found


def audit_page(module, item: dict[str, str]) -> dict[str, object]:
    source = item["source"]
    rows = [line.rstrip() for line in source.splitlines() if line.strip()]
    result: dict[str, object] = {
        "url": item["url"],
        "origin": item["origin"],
        "keywords": rows[0] if rows else "",
        "source_lines": len(rows),
        "recognized": False,
        "unit_count": 0,
        "kinds": {},
        "issues": [],
    }
    issues: list[str] = result["issues"]  # type: ignore[assignment]
    try:
        result["recognized"] = bool(module.is_skill_help_detail(source))
        units = module.parse_help_semantic_units(source)
        result["unit_count"] = len(units)
        kinds: dict[str, int] = {}
        for kind, _value in units:
            kinds[kind] = kinds.get(kind, 0) + 1
        result["kinds"] = kinds
        if not result["recognized"]:
            issues.append("not_recognized_as_help")
        if len(units) < 2:
            issues.append("too_few_semantic_units")

        bullet_count = sum(bool(re.match(r"^\s*-\s+", row)) for row in rows)
        if bullet_count > kinds.get("help_list", 0):
            issues.append("unparsed_list_rows:%d/%d" % (kinds.get("help_list", 0), bullet_count))

        tree_count = sum(bool(module.HELP_SPELLGROUP_ENTRY.fullmatch(row)) for row in rows)
        if tree_count > kinds.get("help_tree", 0):
            issues.append("unparsed_spellgroup_rows:%d/%d" % (kinds.get("help_tree", 0), tree_count))

        raw_commands = sum(kind in {"raw", "help_command", "help_option", "help_tag"} for kind, _value in units)
        has_command_section = (
            any(row.strip().lower() in {"usage:", "syntax:", "format:"} for row in rows) and
            any(module.is_help_usage_command(row.strip()) or module.parse_help_command_row(row) or
                module.HELP_TAG_ROW.fullmatch(row) for row in rows)
        )
        if has_command_section and raw_commands == 0:
            issues.append("command_section_without_protected_commands")

        known_labels = {
            "keywords are", "skill", "spell", "mana", "int", "wis", "chr", "str", "dex", "con",
            "lvl", "requires", "group", "speed", "damage type", "damage", "usage", "syntax", "format",
            "summary", "possible values", "related",
        }
        unknown = []
        for row in rows:
            label = re.match(r"^([A-Za-z][A-Za-z ]{1,30}):", row.strip())
            if label and label.group(1).strip().lower() not in known_labels:
                unknown.append(label.group(1).strip())
        if unknown:
            issues.append("unknown_labels:" + ",".join(sorted(set(unknown))))
    except Exception as error:
        issues.append("parser_exception:%s:%s" % (type(error).__name__, error))
        result["traceback"] = traceback.format_exc()
    return result


def run_regressions(run_dir: Path) -> tuple[list[str], Path]:
    log_path = run_dir / "regression-tests.log"
    failures: list[str] = []
    tests = sorted((ROOT / "tools").glob("test_*.py"))
    env = os.environ.copy()
    temp = run_dir / "test-tmp"
    temp.mkdir(parents=True, exist_ok=True)
    env["TEMP"] = str(temp)
    env["TMP"] = str(temp)
    with log_path.open("w", encoding="utf-8") as log:
        for index, test in enumerate(tests, 1):
            progress("[測試 %d/%d] %s" % (index, len(tests), test.name))
            completed = subprocess.run(
                [sys.executable, str(test)], cwd=str(ROOT), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
            )
            log.write("\n===== %s =====\n%s" % (test.name, completed.stdout))
            if completed.returncode:
                failures.append(test.name)
    return failures, log_path


def write_report(run_dir: Path, results: list[dict[str, object]], download_errors: list[str],
                 regression_failures: list[str], regression_log: Path) -> Path:
    issue_rows = [row for row in results if row["issues"]]
    origins: dict[str, int] = {}
    for row in results:
        origin = str(row["origin"])
        origins[origin] = origins.get(origin, 0) + 1
    lines = [
        "# Alter Aeon Help 全量結構稽核報告",
        "",
        "產生時間：%s" % datetime.now().astimezone().isoformat(timespec="seconds"),
        "",
        "## 摘要",
        "",
        "- 不重複 Help 樣本：%d" % len(results),
        "- 官方網站樣本：%d" % origins.get("official", 0),
        "- 本機紀錄樣本：%d" % origins.get("trace", 0),
        "- 有結構警告的樣本：%d" % len(issue_rows),
        "- 下載錯誤：%d" % len(download_errors),
        "- 回歸測試失敗：%d" % len(regression_failures),
        "",
        "## 回歸測試",
        "",
        "- 結果：%s" % ("通過" if not regression_failures else "失敗"),
        "- 紀錄：`%s`" % regression_log.name,
    ]
    if regression_failures:
        lines.append("- 失敗項目：" + ", ".join(regression_failures))
    if download_errors:
        lines.extend(["", "## 下載錯誤", ""])
        lines.extend("- " + value for value in download_errors)
    lines.extend(["", "## 結構警告", ""])
    if not issue_rows:
        lines.append("沒有發現結構警告。")
    else:
        for row in issue_rows:
            lines.extend([
                "### %s" % row["keywords"],
                "",
                "- 來源：`%s`" % row["origin"],
                "- 網址／檔案：%s" % row["url"],
                "- 原始行數：%s；語意單位：%s" % (row["source_lines"], row["unit_count"]),
                "- 問題：%s" % "; ".join(row["issues"]),
                "",
            ])
    report = run_dir / "HELP_CORPUS_AUDIT_REPORT.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    LATEST_REPORT.write_text(report.read_text(encoding="utf-8"), encoding="utf-8")
    return report


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = OUTPUT_ROOT / ("run-" + stamp)
    run_dir.mkdir(parents=True, exist_ok=False)
    LATEST_POINTER.write_text(str(run_dir.resolve()), encoding="utf-8")
    progress("Alter Aeon Help 全量結構稽核")
    progress("輸出位置：%s" % run_dir)
    progress("階段 1/4：正在尋找官方 Help 分類")

    download_errors: list[str] = []
    official: list[dict[str, str]] = []
    try:
        index = fetch(HELP_INDEX, "help index")
        categories = [url for url in hrefs(index, HELP_INDEX) if re.fullmatch(r"https?://alteraeon\.com:8081/helpdir/\d+", url)]
    except Exception as error:
        categories = []
        download_errors.append(str(error))
    progress("找到 %d 個 Help 分類。" % len(categories))

    leaf_urls: set[str] = set()
    for index, url in enumerate(categories, 1):
        try:
            document = fetch(url, "分類 %d/%d" % (index, len(categories)))
            leaf_urls.update(
                link for link in hrefs(document, url)
                if re.fullmatch(r"https?://alteraeon\.com:8081/helpdir/\d+/\d+", link)
            )
        except Exception as error:
            download_errors.append(str(error))

    leaf_urls = set(sorted(leaf_urls))
    progress("階段 2/4：正在慢速下載 %d 個 Help 頁面" % len(leaf_urls))
    for index, url in enumerate(sorted(leaf_urls), 1):
        try:
            document = fetch(url, "頁面 %d/%d" % (index, len(leaf_urls)))
            source = extract_help_text(document)
            if source.startswith("Keywords are:"):
                official.append({"url": url, "source": source, "origin": "official"})
            else:
                download_errors.append("no help text extracted: " + url)
        except Exception as error:
            download_errors.append(str(error))

    progress("階段 3/4：正在分析官方頁面與本機翻譯紀錄")
    combined = official + trace_sources()
    unique: dict[str, dict[str, str]] = {}
    for item in combined:
        unique.setdefault(item["source"], item)
    module = load_worker()
    results = []
    for index, item in enumerate(unique.values(), 1):
        if index == 1 or index % 100 == 0 or index == len(unique):
            progress("[分析 %d/%d]" % (index, len(unique)))
        results.append(audit_page(module, item))
    with (run_dir / "help-pages.jsonl").open("w", encoding="utf-8") as output:
        for item in unique.values():
            output.write(json.dumps(item, ensure_ascii=False) + "\n")
    with (run_dir / "audit-results.jsonl").open("w", encoding="utf-8") as output:
        for item in results:
            output.write(json.dumps(item, ensure_ascii=False) + "\n")

    progress("階段 4/4：正在執行原始碼回歸測試")
    regression_failures, regression_log = run_regressions(run_dir)
    report = write_report(run_dir, results, download_errors, regression_failures, regression_log)
    warnings = sum(bool(item["issues"]) for item in results)
    progress("")
    progress("稽核完成")
    progress("頁面／樣本：%d" % len(results))
    progress("結構警告：%d" % warnings)
    progress("下載錯誤：%d" % len(download_errors))
    progress("回歸測試：%s" % ("通過" if not regression_failures else "失敗"))
    progress("本次報告：%s" % report)
    progress("最新報告：%s" % LATEST_REPORT)
    return 0 if not regression_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
