import importlib.util
from pathlib import Path
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"
PLUGIN = ROOT / "src/mush-z/worlds/plugins/Translation_Mode.xml"
NVDA_MODULE = ROOT / "src/nvda-addon/appModules/mushclient.py"
SPEC = importlib.util.spec_from_file_location("translation_worker_outgoing_test", WORKER)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


NO_CACHE = {
    "translation_cache_enabled": False,
    "source_language": "en",
    "target_language": "zh",
    "translation_cache_version": 99,
}


def fake_completion(text, _config):
    outputs = {
        "你好": "Hello",
        "我在 ZXQTERM0000QXZ 等你，快過來！":
            "I'm waiting for you at ZXQTERM0000QXZ, come quickly!",
    }
    return outputs[text]


class OutgoingChatIntegrationTests(unittest.TestCase):
    def test_known_channel_translation(self):
        self.assertEqual(
            MODULE.translate_outgoing_chat("chat 你好", NO_CACHE, fake_completion),
            "chat Hello",
        )

    def test_tell_target_and_english_place_name_are_protected(self):
        self.assertEqual(
            MODULE.translate_outgoing_chat(
                "tell John 我在 Dragon Mountain 等你，快過來！", NO_CACHE, fake_completion
            ),
            "tell John I'm waiting for you at Dragon Mountain, come quickly!",
        )

    def test_custom_channel_forms(self):
        for source, expected in (
            ("$friends 你好", "$friends Hello"),
            ("channel send friends 你好", "channel send friends Hello"),
            ("%send friends 你好", "%send friends Hello"),
            ("#你好", "#Hello"),
        ):
            with self.subTest(source=source):
                self.assertEqual(
                    MODULE.translate_outgoing_chat(source, NO_CACHE, fake_completion), expected
                )

    def test_gameplay_commands_are_never_guessed(self):
        for source in ("kill dragon 你好", "cast heal John", "get 中文劍"):
            with self.subTest(source=source):
                with self.assertRaisesRegex(RuntimeError, "UNSUPPORTED_CHAT_COMMAND"):
                    MODULE.translate_outgoing_chat(source, NO_CACHE, fake_completion)

    def test_missing_or_repeated_protected_terms_are_rejected(self):
        for bad in ("Term vanished", "ZXQTERM0000QXZ ZXQTERM0000QXZ"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(RuntimeError, "PROTECTED_TERM"):
                    MODULE.translate_outgoing_chat(
                        "chat 我在 Dragon Mountain 等你", NO_CACHE, lambda _text, _config: bad
                    )

    def test_plugin_replaces_key_without_sending(self):
        xml = PLUGIN.read_text(encoding="utf-8")
        self.assertIn(
            'Accelerator("ctrl+shift+y", "translation_translate_outgoing_chat")', xml
        )
        function = xml.split("function TranslateOutgoingChatInput()", 1)[1].split("\nend", 1)[0]
        self.assertIn("GetCommand()", function)
        self.assertNotIn("Send(", function)
        self.assertNotIn("SendImmediate(", function)
        nvda_source = NVDA_MODULE.read_text(encoding="utf-8")
        self.assertNotIn('gesture="kb:control+shift+y"', nvda_source)

    def test_selected_cloud_provider_is_preferred(self):
        settings = {
            "service": 1, "allow_private_messages": True,
            "azure_region": "global", "timeout_seconds": 1.5,
        }
        candidates = [(1, "secret-not-logged", settings)]
        with mock.patch.object(MODULE, "cloud_translation_config", return_value=settings), \
             mock.patch.object(MODULE, "cloud_translation_candidates", return_value=candidates), \
             mock.patch.object(
                 MODULE.cloud_translation_client, "translate_many_zh_en", return_value=["Hello"]
             ) as cloud, \
             mock.patch.object(
                 MODULE, "completion_zh_en_once", side_effect=AssertionError("LMT should not run")
             ):
            self.assertEqual(MODULE.translate_outgoing_chat("chat 你好", NO_CACHE), "chat Hello")
        cloud.assert_called_once()

    def test_private_message_setting_keeps_tell_offline(self):
        settings = {
            "service": 1, "allow_private_messages": False,
            "azure_region": "global", "timeout_seconds": 1.5,
        }
        with mock.patch.object(MODULE, "cloud_translation_config", return_value=settings), \
             mock.patch.object(MODULE, "cloud_translation_candidates") as candidates, \
             mock.patch.object(MODULE, "completion_zh_en_once", return_value="Hello") as lmt:
            self.assertEqual(
                MODULE.translate_outgoing_chat("tell John 你好", NO_CACHE), "tell John Hello"
            )
        candidates.assert_not_called()
        lmt.assert_called_once()


if __name__ == "__main__":
    unittest.main()
