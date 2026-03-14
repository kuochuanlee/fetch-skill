# AI Agent Skill 索引自動化工具

本專案旨在自動化抓取、解析並彙整來自 GitHub 的 AI Agent Skill 資源，建立一個結構化的索引檔案（index.json），方便開發者快速查找與下載現有的 Skill 功能進行研究。

## 程式架構

專案由兩個核心腳本組成，採用零外部依賴設計：

1.  **setup.ps1 (環境修復腳本)**
    *   目的：解決 Windows/MSYS2/Scoop 環境下 Python 無法驗證 SSL 憑證的問題。
    *   功能：從官方下載最新的 CA 憑證，存放在使用者目錄（`$HOME/.python-certs/`），並設定全域環境變數 `SSL_CERT_FILE`。

2.  **fetcher.py (核心管理腳本)**
    *   目的：執行深度爬取、索引生成與 Skill 下載。
    *   功能：
        *   `update`: 解析種子連結，增量抓取 600+ 個 Skill 的詳細資訊，生成帶 ID 的索引表。
        *   `fetch [ID]`: 根據索引編號，自動下載該 Skill 的核心文件（`SKILL.md`, `README.md` 等）至本地 `downloads` 目錄。

## Skill 更新與快取規則

為了平衡掃描效率與資料準確性，`fetcher.py` 遵循以下更新邏輯：

*   **增量更新機制**：每次執行 `update` 時，腳本會比對 `index.json` 中的快取資料，僅對符合條件的項目發起網路請求。
*   **重新掃描週期**：
    *   **掃描成功項目**：每 **15 天** 重新整理一次（`RETRY_SUCCESS_AFTER_DAYS`）。
    *   **掃描失敗項目**：每 **3 天** 嘗試重新連結一次（`RETRY_FAILED_AFTER_DAYS`）。
*   **ID 一致性**：索引 ID 是根據 `index.json` 的順序自動生成的。請勿手動刪除或修改 `index.json`，否則會導致 ID 與先前紀錄不符。
*   **深度掃描優先級**：針對每個 Skill，腳本會依序嘗試抓取 `SKILL.md`、`README.md` 或 `index.md` 來提取正確的標題與功能描述。

## 標準開發環境配置

本專案開發建議使用 Scoop 安裝的 Python 版本：

1.  **建立虛擬環境**：
    ```powershell
    python -m venv .venv
    ```
2.  **啟動虛擬環境**：
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
執行增量深度掃描，產生帶有 ID 編號的 `index.json`：
```bash
python fetcher.py update
```

### 第三步：查找與下載
1.  透過 MCP Tool `list` 或直接查看 `index.json`，使用關鍵字查找感興趣的 Skill 並記錄其 **ID**。
2.  執行以下指令下載該 Skill 進行研究：
    ```bash
    # 假設要下載 ID 為 42 的項目
    python fetcher.py fetch 42
    ```
3.  下載的內容將儲存在 `downloads/` 目錄下。

## 注意事項

1.  **數據持久化**：腳本會生成 `index.json` 檔案以儲存抓取的元數據，這是維持 ID 一致性的核心，請妥善保存。
2.  **SSL 憑證**：若出現連線錯誤，請確認 `$HOME/.python-certs/cacert.pem` 是否存在，或重新執行 `setup.ps1`。
3.  **檔案規範**：所有腳本、註解與輸出訊息均不包含 Emoji。所有路徑皆採動態取得方式。

## 檔案說明
*   `setup.ps1`: 環境設定與憑證修復。
*   `fetcher.py`: 索引更新與下載管理工具。
*   `server.py`: MCP 伺服器，提供 list, update, fetch 工具。
*   `index.json`: 內部使用的數據快取檔案。


