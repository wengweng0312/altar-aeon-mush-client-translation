# Alter Aeon / Mush-Z 中文翻譯模式

這是一套提供給 Alter Aeon、Mush-Z 與 NVDA 玩家使用的中文翻譯工具。

它可以把遊戲中的英文內容翻譯成中文，保留英文原文供玩家查閱，也支援使用中文撰寫聊天訊息後翻譯成英文。翻譯失敗時會保留英文，不會因為翻譯器故障而讓遊戲內容消失。

## 第一次安裝

### 一、安裝 Mush-Z

1. 前往 [Mush-Z 官方網站](https://www.mush-z.com/)。
2. 選擇 Light 或 Full 版本，兩種都可以使用本翻譯套件。
3. 按照安裝程式的提示完成安裝。
4. 開啟 Mush-Z，確認遊戲畫面中可以看到 `Welcome to Alter Aeon`。
5. 關閉 MUSHclient。

### 二、安裝中文翻譯套件

1. [點此下載 Full 版中文翻譯套件](https://github.com/wengweng0312/altar-aeon-mush-client-translation/releases/download/v0.1.1/Mush-Z_Translation_Mode_Full_v0.1.1.zip)。
2. 下載完成後，解壓縮到 Mush-Z 的安裝目錄。請選擇能直接看到 `docs`、`worlds` 等資料夾的那一層。
3. Windows 詢問是否合併資料夾或覆蓋檔案時，請選擇覆蓋。
4. 重新開啟 Mush-Z。
5. 按 `Ctrl+Shift+P` 開啟 Plugin 清單。
6. 找到並執行 `Add`。
7. 檔案選擇視窗通常會停在 `Mush-Z\worlds\plugins`。如果沒有，請自行進入這個資料夾。
8. 找到 `Translation_Mode.xml`，按 Enter 載入。
9. 如果出現確認視窗，選擇 `OK`。

### 三、安裝 NVDA 附加元件

NVDA 附加元件位於：

```text
Mush-Z\worlds\plugins\translation_bridge\Mush_Client_Translation_Review_v3.nvda-addon
```

執行這個檔案，按照 NVDA 的提示完成安裝並重新啟動 NVDA。

這個步驟也可以交給自動更新器完成：關閉 Mush-Z 後再重新開啟，如果出現更新提示，先選擇 `Yes` 同意更新，再依提示選擇 `No` 讓 MUSHclient 關閉。下載及安裝完成後，系統會自動開啟 NVDA 附加元件的安裝視窗。

完成以上步驟後即可開始使用。

## 基本使用方式

翻譯模式預設會自動開啟。如果尚未開啟，或想暫時停用翻譯，可以按：

```text
Ctrl+Shift+T
```

這個快速鍵會在以下兩種狀態間切換：

- 中文翻譯與中文檢閱模式。
- 翻譯模式關閉，恢復原本的 Mush-Z 行為。

第一次啟動離線翻譯時，模型可能需要一點時間載入。沒有 NVIDIA 顯示卡也可以使用，程式會依照電腦可用的硬體自動選擇執行方式。

## 使用 NVDA 查看翻譯紀錄

安裝附加元件並開啟翻譯模式後，可以使用小鍵盤瀏覽中文翻譯紀錄：鍵盤瀏覽中文翻譯紀錄：

- 小鍵盤 `7`：上一行翻譯紀錄。
- 小鍵盤 `9`：下一行翻譯紀錄。
- `Shift+小鍵盤 7`：跳到最上方。
- `Shift+小鍵盤 9`：跳到最下方。
- 小鍵盤 `4`／`6`：瀏覽中文句子或英文單字。
- 小鍵盤 `1`／`3`：逐字元移動。
- `Shift+小鍵盤 1`／`3`：目前行的行首／行尾。
- 小鍵盤 `2`：讀出目前字元。
- 小鍵盤 `5`：讀出目前單字。
- 小鍵盤 `8`：讀出目前整行。

英文原文會保留在翻譯紀錄中。玩家平常可以直接閱讀中文，遇到名稱、地標、物品或翻譯不確定時，再往右查看英文原文。


## 使用中文與英文玩家聊天

先在 MUSHclient 的指令輸入框輸入中文訊息，例如：

```text
chat 有沒有人可以帶我去練功？
```

按下：

```text
Ctrl+Shift+Y
```

翻譯完成後，輸入框會改成英文。`chat`、`say`、`tell 玩家名稱` 等指令部分會被保留，不會自動送出。請先確認翻譯結果，再按 Enter 傳送。

如果翻譯失敗，原本輸入的中文會保留，也不會自行送到遊戲中。

## 修正錯誤快取

如果某一筆翻譯曾經被打斷，之後一直出現同一個錯誤結果，可以在該內容出現後按：

```text
Ctrl+Shift+Delete
```

這會清除最近五筆翻譯快取，讓它們下次出現時重新翻譯。

## 查看線上 API 用量

翻譯模式開啟時，在 MUSHclient 指令輸入框輸入：

```text
check_api
```

系統會依序報告 Microsoft Azure、Google Cloud 與 DeepL 的設定狀態。DeepL
可直接顯示官方已用、上限及剩餘字元；Azure 與 Google 則顯示此外掛從本版開始
記錄的本機送出字元數。查詢不會送出測試翻譯，也不會顯示 API 金鑰。

## 離線與線上翻譯

Full 版已包含離線 LMT 翻譯模型，不需要另外安裝 Python，也不需要申請 API 金鑰。預設設定即可完全離線使用。

如果希望改用 Microsoft Azure Translator、Google Cloud Translation 或 DeepL，可以編輯：

```text
Mush-Z\worlds\plugins\translation_bridge\cloud_translation_config.txt
```

檔案內有服務編號及填寫說明。請只在自己的電腦填入 API 金鑰，不要把填好的檔案傳給別人或上傳到網路。

私人訊息預設不會送往線上翻譯服務。即使線上服務無法使用，遊戲仍可繼續運作，並依設定使用離線翻譯或英文原文。

## 自動更新

Mush-Z 啟動時會自動檢查翻譯套件是否有新版本。玩家同意更新後，程式會：

1. 關閉 MUSHclient。
2. 下載更新。
3. 備份並安裝新版檔案。
4. 開啟 NVDA 附加元件安裝檔。
5. 清理下載時產生的暫存檔案。

更新失敗時會保留原本可用的版本。已經安裝過 Full 版的玩家，之後通常不需要再次下載整個模型。

所有正式版本與更新說明都可以在 [GitHub Releases](https://github.com/wengweng0312/altar-aeon-mush-client-translation/releases) 查看。

## 重要提醒

- Mush-Z 本體必須由玩家自行從官方網站下載；本專案只提供翻譯相關檔案。
- 請勿刪除 `translation_bridge` 中的模型、執行環境或附加元件檔案。
- 翻譯紀錄可能包含遊戲頻道、對話或私人訊息，請不要隨意上傳或公開。
- Translation Mode 不會自動移動角色、戰鬥或操作遊戲。
- 無論翻譯模型、網路服務或快取發生什麼問題，原始英文都應該保留下來。
這個plugin 是第一次做，陸續也遇到很多問題，也不能保證玩家體驗感滿分，如果遇到問題，可以與我聯絡。
email:wengweng@mail.batol.net

line id:1324967rabbit
