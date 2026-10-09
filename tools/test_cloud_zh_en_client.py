import importlib.util
from pathlib import Path
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = ROOT / "src/mush-z/worlds/plugins/translation_bridge/cloud_translation_client.py"
SPEC = importlib.util.spec_from_file_location("cloud_translation_client_zh_en_test", CLIENT_PATH)
CLIENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLIENT)


class CloudZhEnClientTests(unittest.TestCase):
    def test_azure_direction(self):
        with mock.patch.object(
            CLIENT, "_post_json", return_value=[{"translations": [{"text": "Hello"}]}]
        ) as post:
            self.assertEqual(CLIENT.translate_many_zh_en(1, ["你好"], "key"), ["Hello"])
        url, _headers, payload, _timeout, _opener = post.call_args.args
        self.assertIn("from=zh-Hant", url)
        self.assertIn("to=en", url)
        self.assertEqual(payload, [{"Text": "你好"}])

    def test_google_direction(self):
        response = {"data": {"translations": [{"translatedText": "Hello"}]}}
        with mock.patch.object(CLIENT, "_post_json", return_value=response) as post:
            self.assertEqual(CLIENT.translate_many_zh_en(2, ["你好"], "key"), ["Hello"])
        payload = post.call_args.args[2]
        self.assertEqual(payload["source"], "zh-TW")
        self.assertEqual(payload["target"], "en")

    def test_deepl_direction(self):
        with mock.patch.object(
            CLIENT, "_post_json", return_value={"translations": [{"text": "Hello"}]}
        ) as post:
            self.assertEqual(CLIENT.translate_many_zh_en(3, ["你好"], "key:fx"), ["Hello"])
        url, _headers, payload, _timeout, _opener = post.call_args.args
        self.assertIn("api-free.deepl.com", url)
        self.assertEqual(payload["source_lang"], "ZH")
        self.assertEqual(payload["target_lang"], "EN")


if __name__ == "__main__":
    unittest.main()
