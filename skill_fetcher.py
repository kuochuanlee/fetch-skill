import urllib.request
from urllib.parse import urlparse
import re
import os
import ssl
import json
import sys
import tempfile
import shutil
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 設定
SEED_URL = "https://raw.githubusercontent.com/VoltAgent/awesome-agent-skills/main/README.md"
DATA_FILE = "skills.json"
MAX_WORKERS = 15
MAX_DESC_LENGTH = 1000
RETRY_FAILED_AFTER_DAYS = 7  # 失敗項目每 7 天才重試一次
DEBUG = False

# 全域快取
_SSL_CONTEXT = None

def get_ssl_context():
    global _SSL_CONTEXT
    if _SSL_CONTEXT is not None:
        return _SSL_CONTEXT
    user_home = os.path.expanduser('~')
    cert_path = os.path.join(user_home, '.python-certs', 'cacert.pem')
    context = ssl.create_default_context()
    if os.path.exists(cert_path):
        context.load_verify_locations(cafile=cert_path)
    else:
        print("警告: 自訂憑證不存在，將使用系統預設 SSL 憑證")
    _SSL_CONTEXT = context
    return context

def normalize_url(url):
    if not url: return ""
    url = re.sub(r'/(?:tree|blob)/(?:main|master)', '', url)
    return url.rstrip("/").lower()

def github_to_raw(url):
    if "github.com" not in url: return url, False
    is_file = url.lower().endswith(('.md', '.json', '.txt'))
    raw_url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/").replace("/tree/", "/")
    return raw_url.rstrip("/"), is_file

def fetch_content(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10, context=get_ssl_context()) as response:
            return response.read().decode('utf-8')
    except Exception: return None

def _process_skill_content(skill_dict, content):
    title_match = re.search(r'^#\s+(.*)', content, re.M)
    if title_match: skill_dict['name'] = title_match.group(1).strip()
    features_match = re.search(r'##\s+(?:Features|Functions|Tools|功能)(.*?)(?=##|$)', content, re.S | re.I)
    if features_match:
        desc = features_match.group(1).strip()
        desc = re.sub(r'[\r\n]+', ' ', desc)
        desc = re.sub(r'[*#>`-]', '', desc)
        desc = re.sub(r'\s{2,}', ' ', desc).strip()
        skill_dict['description'] = desc[:MAX_DESC_LENGTH]
    skill_dict['deep_scanned'] = True
    skill_dict['scan_failed'] = False
    skill_dict['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return skill_dict

def extract_deep_info(skill):
    result = skill.copy()
    base_raw_url, is_direct_file = github_to_raw(result['url'])
    if is_direct_file:
        content = fetch_content(base_raw_url)
        if content: return _process_skill_content(result, content)

    base_candidates = [base_raw_url] if len(base_raw_url.split("/")) > 5 else [f"{base_raw_url}/main", f"{base_raw_url}/master"]
    for current_base in base_candidates:
        for filename in ["/SKILL.md", "/README.md", "/index.md"]:
            content = fetch_content(current_base + filename)
            if content: return _process_skill_content(result, content)
    
    # 掃描失敗處理：標記為已掃描但失敗，避免下次立即重試
    result['deep_scanned'] = True
    result['scan_failed'] = True
    result['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return result

def should_retry_failed(skill):
    """判斷失敗項目是否已過冷卻期"""
    updated_at = skill.get('updated_at')
    if not updated_at: return True
    try:
        last_time = datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S")
        return (datetime.now() - last_time).days >= RETRY_FAILED_AFTER_DAYS
    except ValueError: return True

def parse_main_readme(content):
    skills = []
    pattern = r'\[(.*?)\]\((https?://github\.com/.*?)\)(.*)'
    matches = re.finditer(pattern, content)
    seen_urls = set()
    for match in matches:
        name, url, desc_part = match.group(1).strip(), match.group(2).strip(), match.group(3).strip()
        if any(x in url.lower() for x in ["badge", "img.shields.io", "github.com/voltagent/awesome-agent-skills"]): continue
        norm_url = normalize_url(url)
        if norm_url in seen_urls: continue
        seen_urls.add(norm_url)
        try:
            parsed = urlparse(url)
            path_parts = parsed.path.strip('/').split('/')
            github_user = path_parts[0] if path_parts else "Unknown"
        except Exception: github_user = "Unknown"
        skills.append({"name": name, "url": url, "github_user": github_user, "description": re.sub(r'<.*?>', '', desc_part).strip(), "source": url.rstrip('/').split("/")[-2] + "/" + url.rstrip('/').split("/")[-1] if len(url.rstrip('/').split("/")) > 1 else url, "category": "General", "deep_scanned": False, "updated_at": None})
    return skills

def download_skill_recursive(base_raw_url, target_dir, filename, current_depth=0, max_depth=1, processed_files=None):
    if processed_files is None: processed_files = set()
    if current_depth > max_depth or filename in processed_files: return
    processed_files.add(filename)
    base_raw, is_file = github_to_raw(base_raw_url)
    content = None
    if is_file and current_depth == 0: content = fetch_content(base_raw)
    elif len(base_raw.split("/")) <= 5:
        for br in ["main", "master"]:
            content = fetch_content(f"{base_raw}/{br}/{filename.lstrip('/')}")
            if content: break
    else: content = fetch_content(f"{base_raw}/{filename.lstrip('/')}")
    if not content: return
    local_path = os.path.join(target_dir, filename.lstrip('/').replace("/", os.sep))
    if not os.path.realpath(local_path).startswith(os.path.realpath(target_dir)): return
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, "w", encoding="utf-8") as f: f.write(content)
    print(f"  [+] 已下載: {filename}")
    if filename.lower().endswith(".md"):
        links = set(re.findall(r'\[.*?\]\((?!https?://)(.*?\.md)\)', content) + re.findall(r'(?:^|\s|\"|\')([a-zA-Z0-9_\-\./]+\.md)(?:\s|\"|\'|$)', content, re.M))
        for link in links:
            link_clean = link.split("#")[0].strip()
            if link_clean.startswith("/") or "://" in link_clean: continue
            new_filename = os.path.normpath(os.path.join(os.path.dirname(filename), link_clean)).replace(os.sep, "/")
            download_skill_recursive(base_raw_url, target_dir, new_filename, current_depth + 1, max_depth, processed_files)

def download_skill(skill_id):
    if not os.path.exists(DATA_FILE): return print("錯誤: 找不到數據檔案，請先執行 update")
    try:
        target_id = int(skill_id)
        if target_id <= 0: raise ValueError
    except (ValueError, TypeError): return print(f"錯誤: skill_id 必須為正整數")
    with open(DATA_FILE, 'r', encoding='utf-8') as f: skills = json.load(f)
    skill = next((s for s in skills if s['id'] == target_id), None)
    if not skill: return print(f"錯誤: 找不到編號為 {target_id} 的項目")
    target_dir = os.path.join("downloads", re.sub(r'[\\/:*?"<>|.]', '_', skill['name']))
    if not os.path.realpath(target_dir).startswith(os.path.realpath("downloads")): return
    os.makedirs(target_dir, exist_ok=True)
    print(f"正在深度抓取 Skill: {skill['name']}...")
    processed_files = set()
    if skill['url'].lower().endswith('.md'): download_skill_recursive(skill['url'], target_dir, os.path.basename(skill['url']), 0, 1, processed_files)
    for entry in ["SKILL.md", "README.md", "index.md"]: download_skill_recursive(skill['url'], target_dir, entry, 0, 1, processed_files)
    print(f"深度抓取完成！")

def safe_json_write(path, data):
    dir_name = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile(mode='w', dir=dir_name, delete=False, encoding='utf-8') as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp_path = tmp.name
    try: shutil.move(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path): os.remove(tmp_path)

def update_data():
    print("[Incremental Update] 開始執行增量更新 (含失敗冷卻機制)...")
    existing_map = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                existing_map = {normalize_url(s['url']): s for s in json.load(f)}
        except Exception: pass
    main_content = fetch_content(SEED_URL)
    if not main_content: return
    new_list = parse_main_readme(main_content)
    to_scan, final_results, hit_count = [], [], 0
    for skill in new_list:
        norm_url = normalize_url(skill['url'])
        existing = existing_map.get(norm_url)
        if existing and existing.get('deep_scanned'):
            # 如果上次掃描失敗，且還在冷卻期內，則跳過重試，直接用舊的（失敗標記）資料
            if existing.get('scan_failed') and should_retry_failed(existing):
                to_scan.append(skill)
                final_results.append(skill)
            else:
                final_results.append(existing.copy())
                hit_count += 1
        else:
            to_scan.append(skill)
            final_results.append(skill)
    print(f"📊 增量狀態: 快取命中 {hit_count} 項，需掃描 {len(to_scan)} 項。")
    if to_scan:
        print(f"🚀 開始深度掃描...")
        scanned_map = {}
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_url = {executor.submit(extract_deep_info, s): normalize_url(s['url']) for s in to_scan}
            for future in as_completed(future_to_url):
                res = future.result()
                scanned_map[normalize_url(res['url'])] = res
        for i, s in enumerate(final_results):
            nu = normalize_url(s['url'])
            if nu in scanned_map: final_results[i] = scanned_map[nu]
    for idx, skill in enumerate(final_results): skill['id'] = idx + 1
    safe_json_write(DATA_FILE, final_results)
    print(f"🎉 更新完成！數據已儲存。")

def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "fetch" and len(sys.argv) > 2: download_skill(sys.argv[2])
        elif cmd == "update": update_data()
    else: update_data()

if __name__ == "__main__": main()
