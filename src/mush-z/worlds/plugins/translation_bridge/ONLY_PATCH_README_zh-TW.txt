Mush-Z Translation Mode - Only Patch

用途：更新已經安裝完整 Translation Mode 的電腦。

安裝前請完整關閉 MUSHclient，確認 translation worker 與 llama-server 已結束。
將壓縮包內容解壓到 Mush-Z 根目錄並覆蓋同名程式檔案，然後重新開啟 MUSHclient。

Only Patch 不包含 Python runtime、llama.cpp、LMT 模型或 nvdaControllerClient32.dll。
Only Patch 不包含也不會覆蓋：
- cloud_translation_config.txt（雲端服務與 API 金鑰）
- translation_config.json
- translation_cache.sqlite3
- library_glossary_zh_tw.json
- log、history、backend_choice.json 或任何使用者資料

Only Patch 會更新通用且經審核的遊戲、片語與技能詞彙表，以及結構化規則資料庫；這些不是玩家私人設定。

新安裝或缺少模型/runtime 的電腦必須使用 Full Translation Package。
