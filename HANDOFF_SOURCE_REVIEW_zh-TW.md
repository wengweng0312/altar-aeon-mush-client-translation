# Alter Aeon / Mush-Z 中文翻譯模式：原始碼審查 Hand-off

交接日期：2026-10-10  
原始碼版本：v1.2.6 stable  
GitHub：<https://github.com/wengweng0312/altar-aeon-mush-client-translation>

## 給接手 GPT 的第一項指示

請先完整閱讀本文件、`README.md`、主要原始碼與測試，第一輪只做唯讀分析，不要修改檔案。請將發現分成：

1. 已實作且已有測試，不需要重做。
2. 已知限制或仍可重現的錯誤。
3. 看似已實作但測試不足、可能只是局部處理的功能。
4. 規格曾提出但尚未實作的功能。
5. 可能破壞英文 fallback、NVDA、生命週期或更新機制的高風險區域。

先提出證據、可重現方式、風險與建議優先順序，再與使用者確認是否動工。不要看到大型 Python 檔就直接重構，也不要重新研究已淘汰的模型。

## 專案用途

本專案為全盲玩家提供 Alter Aeon / Mush-Z 即時中文資訊層。它不是自動玩遊戲的 AI，也不應自動移動、戰鬥、導航或操作角色。

主要資料流：

```text
Alter Aeon 英文輸出
→ MushReader / Translation_Mode.xml
→ quiet-period 合併與分類
→ translation_bridge inbox
→ persistent translation_worker.pyw
→ 結構化規則、詞彙表、SQLite 快取
→ 離線 LMT 或可選線上翻譯
→ outbox
→ Translation_Mode.xml
→ NVDA 語音與中文檢閱層
```

翻譯紀錄保留中文及英文原文，方便用 NVDA 小鍵盤瀏覽。另支援把 MUSHclient 輸入框中的中文聊天訊息翻成英文，但翻譯後不自動送出。

## 不可犧牲的可靠性規則

- 翻譯 timeout、例外、拒絕、無中文或災難性漏譯：必須保留英文。
- 翻譯失敗不等於沒有輸出。
- LMT、雲端 API、SQLite、glossary、Knowledge Layer 任一故障，遊戲仍需可玩。
- Translation Mode 關閉後恢復原本 Mush-Z 行為。
- 不得自動搶焦點、開啟 history 視窗或移動玩家鍵盤焦點。
- MUSHclient 關閉或 crash 後，worker、SQLite 與其啟動的 llama-server 必須清理。
- 不使用 `taskkill` 清理 worker。
- 私人遊戲紀錄、頻道訊息與 API 金鑰不得自動上傳。
- 結構化判斷若沒有足夠把握，寧可走翻譯與英文 fallback，不可誤改遊戲資訊。

## 目前翻譯引擎

離線基線固定為：

- `NiuTrans/LMT-60-1.7B`
- GGUF：`LMT-60-1.7B-Q4_K_M.gguf`
- llama.cpp / llama-server，使用 `/completion`
- 模型約 1.28 GB
- CPU 可執行，也會依可用環境選擇 GPU/backend

模型與 llama runtime 不放在 Git 原始碼中。正式 Full 套件才包含 portable runtime。此審查包無法單獨進行完整離線推理測試。

已淘汰且不應重新耗時測試：MADLAD-400 3B、NLLB-200 distilled 600M、OPUS-MT en-zh、HPLT translate-en-zh_hant、Tower。現階段沒有更換 LMT 的計畫。

可選線上翻譯：

- Microsoft Azure Translator
- Google Cloud Translation
- DeepL API Free

設定範例位於 `cloud_translation_config.example.txt`。實際 `cloud_translation_config.txt` 被 Git 排除，可能含 API 金鑰。私人訊息預設禁止送往雲端。雲端服務發生錯誤時會暫停／轉用其他已設定服務或 fallback，不應阻塞遊戲。

## 主要原始碼位置

- `src/mush-z/worlds/plugins/Translation_Mode.xml`：MUSHclient 翻譯模式、攔截、history、快捷鍵、worker 生命週期及更新入口。
- `src/mush-z/worlds/plugins/MushReader.xml`：既有 Mush-Z／NVDA 讀取路徑。
- `src/mush-z/worlds/plugins/translation_bridge/translation_worker.py`：可見主 worker 版本。
- `src/mush-z/worlds/plugins/translation_bridge/translation_worker.pyw`：正式無主控台 worker；應與 `.py` 保持一致。
- `src/mush-z/worlds/plugins/translation_bridge/cloud_translation_client.py`：雲端供應商與 fallback。
- `src/mush-z/worlds/plugins/translation_bridge/game_glossary_zh_tw.json`：通用遊戲術語。
- `phrase_glossary_zh_tw.json`、`library_glossary_zh_tw.json`、`skill_glossary_zh_tw.json`、`skill_catalog.json`：短語、技能及圖書館等資料。
- `mush_structure_catalog.sqlite3`：可發布的通用結構資料庫，不是玩家翻譯快取。
- `src/nvda-addon/appModules/mushclient.py`：NVDA 中文檢閱、虛擬 review cursor、小鍵盤操作與排版。
- `tools/`：回歸測試、詞彙表稽核、打包與發布工具。
- `.github/workflows/`：GitHub Release 自動流程。

## 已完成的重要功能

### 翻譯與失敗安全

- persistent worker 與 persistent llama-server。
- heartbeat 管理 MUSHclient session；正常關閉及 stale heartbeat 都會清理 worker、SQLite 與 child server。
- HTTP timeout 約 25 秒，plugin watchdog 約 35 秒。
- catastrophic under-translation guard，避免長房間只剩標題。
- 避免重複／無限迴圈輸出；同時已有針對真實重複物品的例外，避免誤判。
- 最近五筆快取可用 `Ctrl+Shift+Delete` 清除並重新翻譯。
- 翻譯語意或結構更新可透過 cache namespace/version 淘汰舊結果。
- translation trace 與大 log 輪替保留機制。

### 結構化與 glossary

已對大量可靠格式做 deterministic parsing 或欄位級翻譯，包括但不限於：

- skills、單一職業 skills、practice 表格、可用技能清單。
- inventory、carried container、ground container、shop items、shop spells、free items。
- quest/job 標頭、短目標、長描述及附近任務清單。
- identify／裝備屬性、HP、mana、movement、AC、regen、hitroll、damroll 等欄位。
- 房間標題、房間描述、附近預覽、出口與部分方向資訊。
- 常見 get/drop/put/give/wield/carry、隊伍、跟隨、NPC 動作、戰鬥及狀態事件。
- 部分 monster lore、資源、裝備、提示、help 與 wrapped dialogue 排版。
- 技能、遊戲術語、物品屬性與若干通用 NPC 種族／職業詞彙表。

結構化規則為 provider-neutral：在呼叫 LMT、Azure、Google 或 DeepL 前處理可確定的結構，只將未知語意欄位交給翻譯引擎。

最近新增：

- NPC 名字採本機 first-seen 鎖定，同一角色不應在相鄰句子反覆變名；清除最近快取後可重新選擇譯名。
- Linkas 類跟隨／加入隊伍動作保持同一名字。
- `kobold + 明確職業` 完整名詞片語固定，例如 warrior、war leader、mage、cleric、thief、necromancer、druid；不在任意文章中盲目替換。
- monster lore 報告若保留逐行結構，或只把標題與怪物名稱合併，NVDA 會在中英文行數完全吻合時安全逐行配對。

### NVDA 與無障礙

- 中文與英文原文保留在檢閱紀錄。
- 小鍵盤 7／9：上一／下一顯示行；Shift+7／9：頂端／底端。
- 小鍵盤 4／6：中文句子或英文單字；1／3：字元；Shift+1／3：行首／行尾。
- 輸入文字時盡量保留虛擬 review cursor。
- 房間、任務、長 NPC 對話與一般 prose 只有在可安全對齊時才拆成中英配對行。
- 新訊息到達時不應強制把使用者捲到底部。
- 不自動開視窗或搶焦點。

### 操作與發送

- `Ctrl+Shift+T`：中文翻譯／檢閱模式與關閉之間切換；預設 auto start on。
- `Ctrl+Shift+Y`：將目前輸入框中的中文聊天訊息翻成英文；保留 chat、say、tell 對象等指令部分，不自動送出，失敗時保留中文。
- `check_api`：顯示各雲端服務設定與可取得的使用量資訊；Azure／Google 通常只能顯示本機計數，不能代表官方帳戶帳單。
- 簡短測速指令已提供，測速在背景執行，不應讓低階電腦等待數分鐘才可使用。

### 打包、發布與更新

- Full 套件：首次安裝，包含模型與 portable runtime。
- Only Patch：日常更新，不包含模型，也不覆蓋玩家已填寫的雲端設定。
- GitHub Release 發布工具與工作流程。
- Mush-Z 啟動時自動檢查更新，詢問後可關閉 MUSHclient、下載、驗證、備份、覆蓋及啟動 NVDA addon 安裝。
- 更新失敗應回復原版本。
- Only Patch 的 Release 說明應固定指向 Full 版下載。

## 已知限制與值得優先審查之處

### 1. 長輸出仍可能被模型壓成一段

monster lore、房間、quest、help 或混合戰鬥輸出有時在來源中是多行，但 LMT 會把中文前半段合成一段。NVDA 現在只在中英文單位數完全吻合時拆分，以避免錯配。最新 monster lore 修正只處理可靠的「報告標題＋怪物名稱」合併。

請審查是否能在 worker 端先辨識通用報告結構、逐欄翻譯及重建，而不是在 addon 事後猜測。但任何新規則都必須用真實 fixture 驗證，且失敗時維持原文。

### 2. 並非所有 MUD 輸出都已結構化

現有規則主要來自一位玩家長期實戰紀錄與 Mush-Z triggers/filters。其他職業、區域、活動、種族、戰鬥技能和管理訊息可能尚未涵蓋。不可宣稱「所有可結構化內容都已完成」。

請優先找具有穩定起始詞、固定欄位或官方 trigger/filter 證據的格式；不要用少數句子推導會誤判一般文章的寬鬆 regex。

### 3. NPC 名稱一致性不是全球 NPC 字典

目前是本機 first-seen 鎖定，解決上一句「吉姆森」、下一句「金騰」的問題。它不保證首次譯名正確，也不包含完整 Alter Aeon NPC 資料庫。清除最近快取會允許下一次翻譯成為新譯名。

### 4. 種族／職業固定目前是保守完整匹配

`A kobold warrior` 等完整名詞片語會固定翻譯；若它嵌在整個尚未結構化的大段 LMT 輸出裡，模型仍可能產生「矮人戰爭領袖」等錯譯。應評估能否安全抽取 entity field，但不要在任意 prose 中全域替換 `kobold`。

### 5. 繁簡混用尚未根治

模型可能輸出簡體、繁體混合及中國用詞。專案刻意沒有引入 OpenCC；部分重要術語由 deterministic glossary 修正。若提出轉換方案，必須證明不會破壞英文名稱、玩家名稱、遊戲指令、ASCII 欄位與效能。

### 6. 低階電腦的首次長文延遲

相同內容第二次通常命中 SQLite 快取；全新長房間在較慢的 i5-13500H 等 CPU 環境仍可能需要約 6–7 秒。大量結構化已降低呼叫與 API 用量，但自由敘述無法完全表格化。未部署 speculative decoding；過去只建議隔離 A/B，不能假定一定加速或穩定。

### 7. 線上與離線輸出品質不同

Azure 快但可能漏中文、錯譯名稱或改變換行；LMT 品質較好但較慢。provider-neutral 結構應保持共用，但引擎專屬 sanity check 不應誤傷其他 provider。請審查 engine isolation 測試是否涵蓋所有新增規則。

### 8. Review 排版仍是保守 heuristic

房間標題、一般 prose、NPC dialogue、quest、help、monster lore 各有對齊規則。小鍵盤 7／9 偶爾混亂、漏行或整批一行，通常源自翻譯輸出單位與英文原行數不同。不能只看畫面字串；需同時檢查原始 `source`、翻譯 `result`、history 儲存格式與 addon presentation。

### 9. 測試不等於實際 NVDA 驗收

多數測試是離線 fixture、靜態檢查或 mock。最終仍需全盲玩家使用實際 NVDA 驗證焦點、檢閱游標、輸入時定位、戰鬥期間不搶焦點及朗讀順序。

### 10. README 與發行資訊可能逐漸過時

目前程式版本為 v1.2.6，但 README 的 Full 下載連結仍指向固定 v0.1.1 Full 套件；這是刻意重用成熟 Full 基底，但文字應清楚區分「Full 基底版本」與「安裝後由 updater 更新到的程式版本」。README 另有少量重複文字及可再潤飾處。

## 長期構想中尚未完整實作的部分

- 完整 Knowledge Layer：append-only raw JSONL、deterministic observations、derived SQLite、Core／Personal／Community KB 分層。
- 依官方 Wiki 建立完整、經人工審核的技能、物品、區域、NPC 與任務知識庫。
- 對所有職業與所有戰鬥型態的可靠結構化；目前資料偏向現有玩家實際遇到的內容。
- 可證明有收益且不降低穩定性的 speculative decoding 或其他推理加速。
- 完全像中文 MUD、只暴露關鍵英文的顯示模式。曾實驗過純中文／關鍵英文層，但規則與排版風險太高，最後回到較穩定的「中文後接英文」模式。
- 官方 API 帳戶的統一額度查詢。DeepL 可取得官方用量；Azure／Google 金鑰通常不能直接取得完整帳務額度。

## 測試方式

使用可用的 Python 3 執行：

```text
python -m py_compile src/mush-z/worlds/plugins/translation_bridge/translation_worker.py src/mush-z/worlds/plugins/translation_bridge/translation_worker.pyw
python tools/validate_source.py
```

再執行 `tools/test_*.py`。重要測試包括：

- `test_nvda_chinese_display.py`
- `test_room_alignment.py`
- `test_quest_long_description_layout.py`
- `test_semantic_events.py`
- `test_npc_name_consistency.py`
- `test_engine_isolation.py`
- `test_cloud_lazy_lmt_start.py`
- `test_outgoing_chat_integration.py`
- `test_automatic_update.py`
- `test_release_publisher.py`

修改 XML 後要用 XML parser 驗證。修改 `.cmd`／PowerShell 時注意 Windows CRLF，過去曾發生 literal `\n` 破壞批次檔。

若沒有模型、llama-server、MUSHclient 或 NVDA，請明確標示哪些只能靜態／fixture 驗證，不要把 mock PASS 說成實機 PASS。

## 建議審查順序

1. 比較 `.py` 與 `.pyw` 是否完全同步。
2. 追蹤一筆輸出從 XML capture、worker、cache、history 到 NVDA presentation 的完整生命週期。
3. 稽核所有 fallback 分支，確認任何錯誤都不會吞英文。
4. 稽核 structured parser 的 full-match 邊界，找可能誤判一般 prose 的 regex。
5. 稽核 provider isolation，確認 LMT 專屬規則不會影響 Azure／Google／DeepL。
6. 稽核快取 namespace、壞快取淘汰及 Ctrl+Shift+Delete 行為。
7. 稽核 addon 的 7／9、4／6、1／3、Shift 組合鍵與輸入時 cursor 保持。
8. 稽核 updater 的下載驗證、備份、rollback、玩家設定保留及 GitHub URL。
9. 用現有 fixture 找缺口，再提出最小、可逆、可測試的修正。

## 打包內容與隱私說明

本原始碼審查包刻意不包含：

- `.git` 歷史與本機工作區資訊。
- LMT GGUF 模型與 llama runtime。
- 玩家 translation log、trace、accessible history。
- 玩家 SQLite 翻譯快取。
- `cloud_translation_config.txt`、API 金鑰、token。
- deployment backups、dist 套件及暫存測試輸出。

包內的 `mush_structure_catalog.sqlite3` 是專案刻意版本控制的通用結構資料庫，不是私人玩家資料。

## 與使用者合作方式

使用者不是程式設計師，但非常熟悉實際 Alter Aeon、Mush-Z 與 NVDA 操作。他會以真實遊戲輸出描述問題，常會說「黏成一行」、「小鍵盤 7／9 看不到」、「fallback」或提供中英整段文字。

請將這些描述轉成可驗證的資料流問題，不要要求使用者理解 Python、regex 或資料庫。先告訴他你從 log／source 看到的證據，再說能否可靠修復。需要實機驗證時，給一個短而明確的操作步驟。未經明確要求，不要替他重啟 NVDA、MUSHclient，也不要發布 GitHub Release。

