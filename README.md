# Alter Aeon / Mush-Z Translation Mode

這個 repository 用來維護 Mush-Z 的離線／線上中文翻譯模式，以及未來的安全更新器。

目前工程基線：

- Mush-Z plugin 捕捉 Alter Aeon 英文輸出。
- 本地 LMT-60 1.7B Q4 翻譯，亦可選用線上翻譯服務。
- 翻譯失敗、逾時或輸出不完整時，必須回退原始英文。
- 中文透過 NVDA 無障礙朗讀與檢閱附加元件呈現。
- 關閉 MUSHclient 後，worker、SQLite 與它啟動的 llama-server 必須正常結束。
- 不自動操作角色、不搶鍵盤焦點、不自動上傳遊戲紀錄。

## Repository 安全規則

這裡只保存可公開檢查的程式碼、結構化資料與文件。以下內容不得提交：

- 玩家遊戲紀錄、頻道內容及私人訊息
- 翻譯 trace、worker log 與 accessible history
- SQLite 翻譯快取
- API key、GitHub token 或其他憑證
- 使用者本機設定與 session heartbeat
- GGUF 模型、llama.cpp runtime 及產生的完整安裝包
- 臨時檔、備份檔與 Python cache

## 預定更新方式

正式版本將透過 GitHub Releases 發布版本資訊、Only Patch、SHA-256 檢查碼與更新說明。更新器必須先下載與驗證，再備份和替換；任何失敗都不能破壞既有可運作版本。

目前 repository 尚在安全整理階段，尚未提供自動更新。
