# AI Agent Skill 索引自動化工具

本專案旨在自動化抓取、解析並彙整來自 GitHub 的 AI Agent Skill 資源，建立一個結構化的索引檔案（skill-index.md），方便開發者快速查找與複用現有的 Skill 功能。

## 程式架構

專案由兩個核心腳本組成，採用零外部依賴設計，確保在各種 Python 環境下皆可運行：

1.  setup.ps1 (環境修復腳本)
    *   目的：解決 Windows/MSYS2/Scoop 環境下 Python 無法驗證 SSL 憑證的問題。
    *   功能：從 curl.se 下載最新的 CA 憑證，存放在使用者目錄（$HOME/.python-certs/），並設定全域環境變數 SSL_CERT_FILE。
    *   優點：一次執行，全域生效，不受專案資料夾刪除影響。

2.  skill_fetcher.py (核心抓取腳本)
    *   目的：執行深度爬取並生成索引。
    *   功能：
        *   解析 awesome-agent-skills 的 README 獲取種子連結。
        *   使用 ThreadPoolExecutor 進行多執行緒並行抓取。
        *   自動將 GitHub 網址轉換為 Raw 路徑，並深度掃描 SKILL.md 或 README.md 以提取精確標題與功能描述。
    *   優點：無需安裝任何 pip 套件，內建 SSL 憑證自動載入邏輯（優先讀取 $HOME/.python-certs/cacert.pem）。

## 標準開發環境配置 (依據 GEMINI.md 規範)

本專案開發建議使用 Scoop 安裝的 Python 版本：

1.  建立虛擬環境：
    ```powershell
    C:\Users\kuoch\scoop\apps\python\current\python.exe -m venv .venv
    ```
2.  啟動虛擬環境：
    ```powershell
    .\.venv\Scripts\activate
    ```
3.  在此環境下執行後續操作。

## 使用方法

### 第一步：環境初始化（僅需執行一次）
開啟 PowerShell 並執行以下命令以修復全域 SSL 憑證問題：
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File setup.ps1
```

### 第二步：執行抓取
在虛擬環境啟動狀態下，執行 Python 腳本生成或更新索引檔案：
```bash
python skill_fetcher.py
```

### 第三步：查閱索引
開啟生成的 skill-index.md，使用關鍵字（如 stripe, postgres, notion）查找所需的 Skill。

## 注意事項

1.  SSL 憑證錯誤：若執行 Python 腳本時仍出現 SSL 驗證失敗，請確保已執行過 setup.ps1。腳本會自動尋找 $HOME/.python-certs/cacert.pem。
2.  全量掃描耗時：目前的腳本設定為全量深度掃描（600+ 項目），完整執行大約需要 2-5 分鐘，進度會顯示在終端機。
3.  GitHub 速率限制：短時間內頻繁執行可能會觸發 GitHub 的 Rate Limit。若發生此情況，請稍候再試。
4.  風格規範：根據專案規範，所有生成的檔案內容、註解及輸出訊息均不包含 Emoji。所有路徑皆採動態取得方式。

## 檔案說明
*   setup.ps1: 環境設定與憑證修復。
*   skill_fetcher.py: 爬蟲與索引生成器。
*   skill-index.md: 自動生成的 Skill 索引表。
