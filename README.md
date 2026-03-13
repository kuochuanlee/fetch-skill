# AI Agent Skill 索引自動化工具

本專案旨在自動化抓取、解析並彙整來自 GitHub 的 AI Agent Skill 資源，建立一個結構化的索引檔案（skill-index.md），方便開發者快速查找與下載現有的 Skill 功能進行研究。

## 程式架構

專案由兩個核心腳本組成，採用零外部依賴設計：

1.  setup.ps1 (環境修復腳本)
    *   目的：解決 Windows/MSYS2/Scoop 環境下 Python 無法驗證 SSL 憑證的問題。
    *   功能：從官方下載最新的 CA 憑證，存放在使用者目錄（$HOME/.python-certs/），並設定全域環境變數 SSL_CERT_FILE。

2.  skill_fetcher.py (核心管理腳本)
    *   目的：執行深度爬取、索引生成與 Skill 下載。
    *   功能：
        *   update: 解析種子連結，並行抓取 600+ 個 Skill 的詳細資訊，生成帶 ID 的索引表。
        *   fetch [ID]: 根據索引編號，自動下載該 Skill 的核心文件（SKILL.md, README.md 等）至本地 downloads 目錄。

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

## 使用方法

### 第一步：環境初始化（僅需執行一次）
修復全域 SSL 憑證問題，確保 Python 具備連線能力：
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File setup.ps1
```

### 第二步：更新索引
執行全量深度掃描，產生帶有 ID 編號的 `skill-index.md`：
```bash
python skill_fetcher.py update
```

### 第三步：查找與下載
1.  開啟 `skill-index.md`，使用關鍵字查找感興趣的 Skill 並記錄其 **ID**。
2.  執行以下指令下載該 Skill 進行研究：
    ```bash
    # 假設要下載 ID 為 42 的項目
    python skill_fetcher.py fetch 42
    ```
3.  下載的內容將儲存在 `downloads/` 目錄下。

## 注意事項

1.  數據持久化：腳本會生成 `skills.json` 檔案以儲存抓取的元數據，請勿手動修改此檔案以維持 ID 一致性。
2.  SSL 憑證：若出現連線錯誤，請確認 $HOME/.python-certs/cacert.pem 是否存在。
3.  檔案規範：所有腳本、註解與輸出訊息均不包含 Emoji。所有路徑皆採動態取得方式。

## 檔案說明
*   setup.ps1: 環境設定與憑證修復。
*   skill_fetcher.py: 索引更新與下載管理工具。
*   skill-index.md: 自動生成的 Skill 索引表（Markdown）。
*   skills.json: 內部使用的數據快取檔案。
