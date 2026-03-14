import json
import logging
import os
import sys
from filelock import FileLock, Timeout  # pip install filelock
from mcp.server.fastmcp import FastMCP
import fetcher

# 設定 logging 確保輸出至 stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr
)

mcp = FastMCP("fetch-skill")
LOCK_FILE = fetcher.DATA_FILE + ".lock"


@mcp.tool()
def list(keyword: str = "", page: int = 1, page_size: int = 20) -> dict:
    """
    列出已索引的技能清單，支援關鍵字過濾與分頁。
    keyword: 過濾名稱或描述，空字串表示不過濾
    page: 頁碼，從 1 開始
    page_size: 每頁筆數，預設 20
    """
    if not os.path.exists(fetcher.DATA_FILE):
        return {"error": "Data file not found. Please run update first."}

    try:
        with open(fetcher.DATA_FILE, 'r', encoding='utf-8') as f:
            skills = json.load(f)

        if keyword:
            kw = keyword.lower()
            skills = [
                s for s in skills
                if kw in s.get('name', '').lower()
                or kw in s.get('description', '').lower()
            ]

        total = len(skills)
        start = (page - 1) * page_size
        paged = skills[start:start + page_size]

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "results": paged
        }
    except Exception as e:
        logging.error(f"list failed: {e}")
        return {"error": str(e)}


@mcp.tool()
def update() -> dict:
    """
    從遠端更新技能索引（增量更新，有快取機制）。
    注意：此操作可能需要數分鐘，視網路狀況而定。
    """
    # 使用 FileLock 防止多個實例同時更新資料庫
    lock = FileLock(LOCK_FILE, timeout=5)
    try:
        with lock:
            fetcher.update()
            if not os.path.exists(fetcher.DATA_FILE):
                return {"error": "Update failed to produce data file."}
                
            with open(fetcher.DATA_FILE, 'r', encoding='utf-8') as f:
                skills = json.load(f)
            return {"status": "ok", "total_skills": len(skills)}
    except Timeout:
        return {"error": "Another update is already in progress."}
    except Exception as e:
        logging.error(f"update failed: {e}")
        return {"error": str(e)}


@mcp.tool()
def fetch(skill_id: int) -> dict:
    """
    下載指定 ID 的技能文件到本地 downloads/ 目錄。
    skill_id: 技能的數字 ID（可從 list 取得）
    """
    if skill_id <= 0:
        return {"error": "skill_id must be a positive integer."}

    try:
        fetcher.fetch(skill_id)
        return {"status": "ok", "skill_id": skill_id}
    except Exception as e:
        logging.error(f"fetch({skill_id}) failed: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run()
