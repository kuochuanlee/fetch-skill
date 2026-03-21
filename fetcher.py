import urllib.request
from urllib.parse import urlparse
import re
import os
import ssl
import json
import sys
import tempfile
import shutil
import threading
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed


# 設定 logging 配置，確保導向 stderr 以免污染 MCP 的 stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr
)


# 強制設定標準輸出編碼為 UTF-8，解決 Windows 終端機亂碼問題
if sys.stdout.encoding != 'utf-8':
    try:
        # Python 3.7+ 支援 reconfigure
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # 舊版本 Python 備用方案
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


# 設定專案全域變數
SEED_URL = "https://raw.githubusercontent.com/VoltAgent/awesome-agent-skills/main/README.md"
DATA_FILE = "skill-index.json"
MAX_WORKERS = 15
MAX_DESC_LENGTH = 1000
RETRY_SUCCESS_AFTER_DAYS = 15  # 成功項目每 15 天刷新一次
RETRY_FAILED_AFTER_DAYS = 3    # 失敗項目每 3 天重試一次
DEBUG = False


# 全域快取與鎖定機制
_SSL_CONTEXT = None
_SSL_LOCK = threading.Lock()


def get_ssl_context():
    global _SSL_CONTEXT

    # 快速檢查是否已有快取
    if _SSL_CONTEXT is not None:
        return _SSL_CONTEXT

    # 使用鎖定確保執行緒安全
    with _SSL_LOCK:
        # 再次檢查，防止雙重初始化
        if _SSL_CONTEXT is not None:
            return _SSL_CONTEXT

        # 設定憑證路徑
        user_home = os.path.expanduser('~')
        cert_path = os.path.join(
            user_home,
            '.python-certs',
            'cacert.pem'
        )
        context = ssl.create_default_context()

        # 載入自訂或系統憑證
        if os.path.exists(cert_path):
            context.load_verify_locations(cafile=cert_path)
        else:
            logging.warning("Custom certificate not found, using system default SSL context")

        _SSL_CONTEXT = context
        return context


def normalize_url(url):
    # 處理空的 URL
    if not url:
        return ""

    # 移除 GitHub 特有的分支路徑
    url = re.sub(r'/(?:tree|blob)/(?:main|master)', '', url)
    return url.rstrip("/").lower()


def github_to_raw(url):
    # 判斷是否為合法 URL 格式
    if not url or not (url.startswith('http://') or url.startswith('https://')):
        return url, False

    # 判斷是否為 GitHub 連結
    if "github.com" not in url:
        return url, False

    # 判斷是否直接指向檔案
    is_file = url.lower().endswith(('.md', '.json', '.txt'))

    # 轉換為 raw 內容連結
    raw_url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/").replace("/tree/", "/")
    return raw_url.rstrip("/"), is_file


def fetch_content(url):
    try:
        # 建立請求並獲取內容
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0'}
        )

        with urllib.request.urlopen(req, timeout=10, context=get_ssl_context()) as response:
            return response.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        logging.error(f"HTTP {e.code}: {url}")
        return None
    except Exception as e:
        logging.error(f"Failed to fetch {url}: {str(e)}")
        return None


def _process_skill_content(
    skill_dict,
    content
):
    # 解析標題
    title_match = re.search(r'^#\s+(.*)', content, re.M)

    if title_match:
        skill_dict['name'] = title_match.group(1).strip()

    # 解析功能描述
    features_match = re.search(r'##\s+(?:Features|Functions|Tools|功能)(.*?)(?=##|$)', content, re.S | re.I)

    if features_match:
        desc = features_match.group(1).strip()
        desc = re.sub(r'[\r\n]+', ' ', desc)
        desc = re.sub(r'[*#>`-]', '', desc)
        desc = re.sub(r'\s{2,}', ' ', desc).strip()
        skill_dict['description'] = desc[:MAX_DESC_LENGTH]

    # 更新掃描狀態
    skill_dict['deep_scanned'] = True
    skill_dict['scan_failed'] = False
    skill_dict['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return skill_dict


def extract_deep_info(skill):
    result = skill.copy()
    base_raw_url, is_direct_file = github_to_raw(result['url'])

    # 如果是直接連結到檔案，直接抓取
    if is_direct_file:
        content = fetch_content(base_raw_url)

        if content:
            return _process_skill_content(result, content)

    # 嘗試多種可能的文件路徑
    if len(base_raw_url.split("/")) > 5:
        base_candidates = [base_raw_url]
    else:
        base_candidates = [f"{base_raw_url}/main", f"{base_raw_url}/master"]

    for current_base in base_candidates:
        for filename in ["/SKILL.md", "/README.md", "/index.md"]:
            content = fetch_content(current_base + filename)

            if content:
                return _process_skill_content(result, content)

    # 掃描失敗處理：標記為已掃描但失敗，避免下次立即重試
    result['deep_scanned'] = True
    result['scan_failed'] = True
    result['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return result


def parse_main_readme(content):
    skills = []
    pattern = r'\[(.*?)\]\((https?://github\.com/.*?)\)(.*)'
    matches = re.finditer(pattern, content)
    seen_urls = set()

    # 疊代解析所有的連結
    for match in matches:
        name = match.group(1).strip()
        url = match.group(2).strip()
        desc_part = match.group(3).strip()

        # 過濾不需要的連結
        if any(x in url.lower() for x in ["badge", "img.shields.io", "github.com/voltagent/awesome-agent-skills"]):
            continue

        norm_url = normalize_url(url)

        if norm_url in seen_urls:
            continue

        seen_urls.add(norm_url)

        try:
            # 解析 GitHub 使用者資訊
            parsed = urlparse(url)
            path_parts = parsed.path.strip('/').split('/')

            if path_parts:
                github_user = path_parts[0]
            else:
                github_user = "Unknown"
        except Exception:
            github_user = "Unknown"

        # 整理來源資訊
        url_parts = url.rstrip('/').split("/")

        if len(url_parts) > 1:
            source = url_parts[-2] + "/" + url_parts[-1]
        else:
            source = url

        # 建立技能資料字典
        skills.append({
            "name": name,
            "url": url,
            "github_user": github_user,
            "description": re.sub(r'<.*?>', '', desc_part).strip(),
            "source": source,
            "category": "General",
            "deep_scanned": False,
            "updated_at": None
        })

    return skills


def download_skill_recursive(
    base_raw_url,
    target_dir,
    filename,
    current_depth=0,
    max_depth=1,
    processed_files=None
):
    # 初始化處理過的檔案記錄
    if processed_files is None:
        processed_files = set()

    # 深度與重複檢查
    if current_depth > max_depth or filename in processed_files:
        return

    processed_files.add(filename)
    base_raw, is_file = github_to_raw(base_raw_url)
    content = None

    # 根據不同情境嘗試獲取內容
    if is_file and current_depth == 0:
        content = fetch_content(base_raw)
    elif len(base_raw.split("/")) <= 5:
        for br in ["main", "master"]:
            content = fetch_content(f"{base_raw}/{br}/{filename.lstrip('/')}")

            if content:
                break
    else:
        content = fetch_content(f"{base_raw}/{filename.lstrip('/')}")

    if not content:
        return

    # 確保路徑安全性 (防止路徑穿越攻擊)
    local_path = os.path.abspath(os.path.join(target_dir, filename.lstrip('/').replace("/", os.sep)))
    target_abs_dir = os.path.abspath(target_dir)

    if not local_path.startswith(target_abs_dir):
        logging.warning(f"Path traversal blocked: {filename}")
        return

    # 建立目錄並寫入檔案
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    with open(local_path, "w", encoding="utf-8") as f:
        f.write(content)

    logging.info(f"  [+] Downloaded: {filename}")

    # 遞迴下載連結的文件
    if filename.lower().endswith(".md"):
        links = set(re.findall(r'\[.*?\]\((?!https?://)(.*?\.md)\)', content) + re.findall(r'(?:^|\s|\"|\')([a-zA-Z0-9_\-\./]+\.md)(?:\s|\"|\'|$)', content, re.M))

        for link in links:
            link_clean = link.split("#")[0].strip()

            if link_clean.startswith("/") or "://" in link_clean:
                continue

            new_filename = os.path.normpath(os.path.join(os.path.dirname(filename), link_clean)).replace(os.sep, "/")
            download_skill_recursive(
                base_raw_url,
                target_dir,
                new_filename,
                current_depth + 1,
                max_depth,
                processed_files
            )


def fetch(skill_id):
    # 檢查資料檔案是否存在
    if not os.path.exists(DATA_FILE):
        raise FileNotFoundError(f"Data file {DATA_FILE} not found. Please run update first.")

    try:
        # 驗證 ID 合法性
        target_id = int(skill_id)

        if target_id <= 0:
            raise ValueError("skill_id must be a positive integer.")
    except (ValueError, TypeError):
        raise ValueError("skill_id must be a positive integer.")

    # 讀取現有資料
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        skills = json.load(f)

    skill = next((s for s in skills if s['id'] == target_id), None)

    if not skill:
        raise ValueError(f"Item with ID {target_id} not found.")

    # 準備下載目錄
    target_dir = os.path.join("downloads", re.sub(r'[\\/:*?"<>|.]', '_', skill['name']))

    if not os.path.realpath(target_dir).startswith(os.path.realpath("downloads")):
        raise PermissionError("Target directory is outside of downloads folder.")

    os.makedirs(target_dir, exist_ok=True)
    logging.info(f"Fetching Skill: {skill['name']}...")
    processed_files = set()

    # 執行下載
    if skill['url'].lower().endswith('.md'):
        download_skill_recursive(
            skill['url'],
            target_dir,
            os.path.basename(skill['url']),
            0,
            1,
            processed_files
        )

    for entry in ["SKILL.md", "README.md", "index.md"]:
        download_skill_recursive(
            skill['url'],
            target_dir,
            entry,
            0,
            1,
            processed_files
        )

    logging.info(f"Fetch completed!")


def fetchall():
    import time
    if not os.path.exists(DATA_FILE):
        raise FileNotFoundError(f"Data file {DATA_FILE} not found. Please run update first.")

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        skills = json.load(f)

    total = len(skills)
    logging.info(f"Starting fetchall for {total} skills. (Sequential download to avoid rate limits)")

    for idx, skill in enumerate(skills, 1):
        logging.info(f"[{idx}/{total}] Processing ID {skill['id']}: {skill['name']}...")
        try:
            fetch(skill['id'])
        except Exception as e:
            logging.error(f"Failed to fetch ID {skill['id']}: {e}")
        time.sleep(0.5)

    logging.info("[Done] Fetchall completed.")


def generate_markdown_index(skills):
    md_path = "skill-index.md"
    lines = [
        "# AI Agent Skills Index",
        "",
        "> 此檔案由 `fetcher.py update` 自動產生，請隨時依此查閱最新的技能清單。",
        "",
        "| ID | 名稱 (Name) | 作者 (Author) | 說明 (Description) |",
        "|---|---|---|---|"
    ]
    
    for s in skills:
        id_str = str(s.get('id', ''))
        name = str(s.get('name', '')).replace('|', '&#124;')
        url = str(s.get('url', ''))
        name_link = f"[{name}]({url})" if url else name
        author = str(s.get('github_user', '')).replace('|', '&#124;')
        desc_raw = str(s.get('description', '')).replace('\n', ' ').replace('\r', '')
        desc = desc_raw[:150] + ('...' if len(desc_raw) > 150 else '')
        desc = desc.replace('|', '&#124;')
        
        lines.append(f"| {id_str} | {name_link} | {author} | {desc} |")
        
    try:
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        logging.info(f"[Done] Generated markdown index at {md_path}")
    except Exception as e:
        logging.error(f"Failed to generate markdown index: {e}")


def safe_json_write(
    path,
    data
):
    # 使用暫存檔安全寫入 JSON
    dir_name = os.path.dirname(os.path.abspath(path))

    with tempfile.NamedTemporaryFile(mode='w', dir=dir_name, delete=False, encoding='utf-8') as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp_path = tmp.name

    try:
        # 原子性移動檔案
        shutil.move(tmp_path, path)
    except Exception as e:
        logging.error(f"Failed to safely write JSON file {path}: {e}")

        # 清理殘留的暫存檔
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        # 重新拋出異常，讓呼叫端知曉失敗
        raise


def update():
    logging.info("[Incremental Update] Starting update...")
    existing_map = {}

    # 讀取既有的資料庫
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                existing_map = {normalize_url(s['url']): s for s in json.load(f)}
        except Exception:
            pass

    # 抓取主要 README 內容
    main_content = fetch_content(SEED_URL)

    if not main_content:
        return

    new_list = parse_main_readme(main_content)
    to_scan, final_results, hit_count = [], [], 0

    # 比對並過濾需要更新的項目
    for skill in new_list:
        norm_url = normalize_url(skill['url'])
        existing = existing_map.get(norm_url)

        # 判斷是否需要重新掃描
        need_re_scan = True

        if existing and existing.get('deep_scanned'):
            updated_at = existing.get('updated_at')
            days_passed = 999  # Forced re-scan if date is missing

            if updated_at:
                try:
                    last_time = datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S")
                    days_passed = (datetime.now() - last_time).days
                except ValueError:
                    pass

            if existing.get('scan_failed'):
                # Failed: Cache for 3 days
                if days_passed < RETRY_FAILED_AFTER_DAYS:
                    need_re_scan = False
            else:
                # Success: Cache for 15 days
                if days_passed < RETRY_SUCCESS_AFTER_DAYS:
                    need_re_scan = False

        if need_re_scan:
            to_scan.append(skill)
            final_results.append(skill)
        else:
            final_results.append(existing.copy())
            hit_count += 1

    logging.info(f"[Status] Cache hit: {hit_count}, To scan: {len(to_scan)}")

    # 執行多執行緒掃描
    if to_scan:
        total_tasks = len(to_scan)
        completed_count = 0
        logging.info(f"[Action] Starting deep scan ({total_tasks} items)...")
        scanned_map = {}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_url = {
                executor.submit(extract_deep_info, s): normalize_url(s['url'])
                for s in to_scan
            }

            for future in as_completed(future_to_url):
                completed_count += 1
                res = future.result()
                scanned_map[normalize_url(res['url'])] = res

                # 顯示掃描進度
                status_str = "[FAIL]" if res.get('scan_failed') else "[OK]"
                logging.info(f"  [{completed_count}/{total_tasks}] {status_str}: {res['name']}")

        # 整合掃描結果與原始列表
        final_results = [
            scanned_map.get(normalize_url(s['url']), s)
            for s in final_results
        ]

    # 重編 ID 並儲存
    for idx, skill in enumerate(final_results):
        skill['id'] = idx + 1

    safe_json_write(DATA_FILE, final_results)
    generate_markdown_index(final_results)
    logging.info(f"[Done] Update completed. Data saved.")


def main():
    # 根據命令列參數決定執行行為
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()

        if cmd == "fetch" and len(sys.argv) > 2:
            try:
                fetch(sys.argv[2])
            except Exception as e:
                logging.error(str(e))
        elif cmd == "update":
            update()
        elif cmd == "fetchall":
            try:
                fetchall()
            except Exception as e:
                logging.error(str(e))
    else:
        update()


if __name__ == "__main__":
    main()
