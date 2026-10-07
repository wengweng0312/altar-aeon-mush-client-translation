Mush-Z Translation Mode Portable 測試包

安裝：
1. 關閉 MUSHclient。
2. 將 ZIP 直接解壓縮到 Mush-Z 根目錄，讓 worlds 資料夾合併。
3. 啟動 Mush-Z，載入 worlds\plugins\Translation_Mode.xml。
4. 第一次啟動會自動測試 CPU 與可用的 Vulkan 後端，之後記住本機選擇。

本包完全離線，不需要安裝 Python，不會修改 Windows PATH。
沒有可用 GPU 時會自動使用 CPU。翻譯失敗時應回退原始英文。

重要：本包包含 Translation Mode 所需的 MushReader.xml 接口版本。若只複製 Translation_Mode.xml 與 translation_bridge，模型雖可顯示 ready，但 MushReader 不會把遊戲文字送入翻譯佇列。

技能 glossary：
skill_glossary_zh_tw.json 是可攜的基礎詞庫。未知技能會由 LMT 翻譯，並只記錄在每位玩家自己的 translation_cache.sqlite3。
不要把玩家的 translation_cache.sqlite3 發布給其他人。

既有結構目錄：
mush_structure_catalog.sqlite3 收錄 Mush-Z 現有 trigger 的格式、具名欄位、用途分類與匿名命中次數，供後續確定性翻譯使用。它不包含玩家看到的原文、頻道訊息或房間內容；資料庫不存在時也不影響原有翻譯。
mush_structure_catalog_report.txt 是可閱讀的摘要。

自行重建乾淨測試包：
執行 translation_bridge\build_translation_package.cmd。
打包器只使用白名單，並排除紀錄、快取、history、API key、備份與機器專屬設定。

Accessibility 驗收仍須由 NVDA 使用者實際完成。Translation Mode 不應自動開啟視窗或搶走焦點。

兩段模式（Ctrl+Shift+T）：
1. 中文檢閱：中文翻譯與朗讀；小鍵盤 7/9 與 Shift+7/9 瀏覽翻譯 history，1/3 逐字，4/6 依目前選取行瀏覽句子或單字。
2. Translation Mode 關閉：完全使用原本 Mush-Z 行為。

中文檢閱需要安裝 Mush_Client_Translation_Review_v3.nvda-addon。未安裝時仍可使用原有 Ctrl+Shift history 快捷鍵。
History 統一使用真正的上下行：完整英文原文合併成一行置頂，中文位於下方；單句也會建立英文、中文兩行。這只改檢閱排版，不改翻譯與快取。
Quest 沿用結構化分類，英文與中文各自依任務名稱、地點、等級、概述、上一目標及目前目標逐類分行；所有英文分類在上、所有中文分類在下。
`skills <職業>` 的固定欄位表格會逐列解析；每一列英文下方緊接對應中文列。技能名稱與依賴名稱才會翻譯，職業欄、等級、練習、百分比、列數及順序由程式保留。舊的整塊合併快取會被繞過。
多句房間同樣是一行英文在上，中文標題與句子各自一行在下。小鍵盤 7/9 每次移動一行，能繼續走到上一個或下一個房間；Ctrl+Shift+PageUp/PageDown 的既有整筆朗讀不變。
小鍵盤 7/9 使用檔案更新偵測取代固定 80 ms 等待；通常約 5 至 10 ms 即完成，慢速情況保留安全上限。

Scan 結構化：`You scan the surrounding area...` 會按方向逐行解析。方向、距離數字、括號方向、已辨識名稱與門狀態不交給模型；只有描述欄位使用片語快取或 LMT。舊的整塊 scan cache 會被繞過，避免黏成一句的結果繼續命中。
房內生物清單結構化：`Mobs in the room with you:` 標題與其後每個生物各自保留一行；若同一批輸出附帶 NPC 抵達或離開訊息，也維持獨立一行。舊的整塊合併快取會被繞過。
歷史 Fallback 修復：空的技能名稱查詢、生命／法力／移動提示、剩餘練習點、遊戲時間、角色與技能等級、MUSHclient 行數統計改由本地固定格式處理，保留所有數字並繞過舊的英文快取。`freak N!` 保留遊戲專用詞與數字，不再交給模型誤改。
History 瀏覽鎖定：用 7／上一筆離開最底端後，新訊息追加時不會把選取位置拉回最新；回到底部才恢復跟隨。跨行 `says/asks/tells` 引號對話會保留成一行完整英文與一行完整中文，不套用房間標點拆行。
新增結構化格式：登入編號選單、Help 搜尋結果、好友登入／離線清單、技能與法術說明頁、裝備建議、帶 Doors 的房間、Tip、Syntax 與書籍本文。固定欄位與每個可操作項目保留獨立行；房間與書籍的畫面折行仍會重新組成完整語意段落。
房間句段快取：全新長房間仍只送出一次模型請求；成功翻譯後，才將能一對一安全對齊的完整句段加入快取。日後遇到部分相同的新房間，只翻譯未命中的句段；句界或完整性無法確認時自動維持整段翻譯，不猜測、不省略。
重複物品修復：inventory、容器與商店等逐行結構化區塊，使用行數、空白列、數字和順序驗證，不再因大量相同物品的中文較短而被散文字數比例誤判。一般翻譯的重複迴圈與漏譯防護維持不變。
Help 語意單位引擎：Help 頁面不再要求 Keywords 必須是第一行；Showing page、Keywords、Skill／Spell、屬性欄位、Usage、原樣指令、完整段落及尾端提示會先拆成有序單位，再逐項翻譯、驗證及重建。舊快取若只是原樣英文會自動重新翻譯；單一單位失敗只回退該段英文，不吞掉整頁。
NVDA add-on v17：Shift+小鍵盤 1／3 分別跳到目前檢閱行的行首／行尾，並同步小鍵盤 4／6 使用的句子／單字位置，不再出現兩套游標。Help 英文依欄位、Usage、指令及完整段落分行；房間英文仍維持單行置頂。
