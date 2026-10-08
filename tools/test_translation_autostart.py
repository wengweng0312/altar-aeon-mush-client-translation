from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "Translation_Mode.xml"


def main() -> None:
    text = PLUGIN.read_text(encoding="utf-8")
    ET.parse(PLUGIN)

    required = (
        'save_state="y"',
        'match="translation_autostart *"',
        'match="translation_benchmark_next_start"',
        'match="lmt_test"',
        'GetVariable("translation_auto_start")',
        'SetVariable("translation_auto_start", "1")',
        'SetVariable("translation_auto_start", "0")',
        'if value == nil or value == "" then',
        'function OnPluginConnect()',
        'if translation_auto_start_enabled() and not enabled then',
        'EnableTranslation(false)',
        'function ToggleTranslation()',
        'EnableTranslation(true)',
        'function ScheduleTranslationBenchmark()',
        'benchmark_lmt_next_start.flag',
    )
    for marker in required:
        assert marker in text, marker

    # Auto-start must not announce or stop speech during world/plugin startup.
    install_start = text.index("function OnPluginInstall()")
    connect_start = text.index("function OnPluginConnect()")
    assert "EnableTranslation(false)" not in text[install_start:connect_start]
    auto_call = text.index("EnableTranslation(false)", connect_start)
    install_end = text.index("function EnableTranslation", auto_call)
    install_body = text[auto_call:install_end]
    assert 'Execute("tts_stop")' not in install_body

    # The mode is only marked enabled after both launchers have succeeded.
    enable_start = text.index("function EnableTranslation")
    enable_end = text.index("function SetTranslationAutoStart", enable_start)
    enable_body = text[enable_start:enable_end]
    assert enable_body.index("start_speech_worker()") < enable_body.index("enabled = true")
    assert enable_body.index("pcall(start_worker)") < enable_body.index("enabled = true")

    print("translation autostart regression: PASS")


if __name__ == "__main__":
    main()
