import urllib.request
import re
import os
import ssl
import json
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 設定
SEED_URL = "https://raw.githubusercontent.com/VoltAgent/awesome-agent-skills/main/README.md"
INDEX_FILE = "skill-index.md"
DATA_FILE = "skills.json"
MAX_WORKERS = 15

def get_ssl_context():
    user_home = os.path.expanduser('~')
    cert_path = os.path.join(user_home, '.python-certs', 'cacert.pem')
    context = ssl.create_default_context()
    if os.path.exists(cert_path):
        context.load_verify_locations(cafile=cert_path)
    return context

def github_to_raw(url):
    raw_url = url.replace("github.com", "raw.githubusercontent.com")
    raw_url = raw_url.replace("/blob/", "/")
    raw_url = raw_url.replace("/tree/", "/")
    raw_url = raw_url.rstrip("/")
    return raw_url

def fetch_content(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10, context=get_ssl_context()) as response:
            return response.read().decode('utf-8')
    except Exception:
        return None

def extract_deep_info(skill):
    base_raw_url = github_to_raw(skill['url'])
    paths_to_try = ["/SKILL.md", "/README.md", "/index.md"]
    
    for filename in paths_to_try:
        content = fetch_content(base_raw_url + filename)
        if content:
            title_match = re.search(r'^#\s+(.*)', content, re.M)
            if title_match:
                skill['name'] = title_match.group(1).strip()
            
            features_match = re.search(r'##\s+(?:Features|Functions|Tools|功能)(.*?)(?=##|$)', content, re.S | re.I)
            if features_match:
                desc = features_match.group(1).strip()
                desc = re.sub(r'[\r\n]+', ' ', desc)
                desc = re.sub(r'[*#>`-]', '', desc)
                skill['description'] = desc[:200]
            
            skill['deep_scanned'] = True
            return skill
    return skill

def parse_main_readme(content):
    skills = []
    pattern = r'\[(.*?)\]\((https?://github\.com/.*?)\)(.*)'
    matches = re.finditer(pattern, content)
    
    seen_urls = set()
    for match in matches:
        name = match.group(1).strip()
        url = match.group(2).strip()
        desc_part = match.group(3).strip()
        
        if any(x in url.lower() for x in ["badge", "img.shields.io", "github.com/voltagent/awesome-agent-skills"]):
            continue
        
        if url in seen_urls:
            continue
        seen_urls.add(url)
        
        # 提取 GitHub 帳號名稱
        url_parts = url.split("/")
        # 通常格式為 https://github.com/USER/REPO/...
        github_user = url_parts[3] if len(url_parts) > 3 else "Unknown"
            
        skills.append({
            "name": name,
            "url": url,
            "github_user": github_user,
            "description": re.sub(r'<.*?>', '', desc_part).strip(),
            "source": url.split("/")[-2] + "/" + url.split("/")[-1],
            "category": "General",
            "deep_scanned": False
        })
    
    for idx, skill in enumerate(skills):
        skill['id'] = idx + 1
        
    return skills

def generate_markdown(skills):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"""# AI Agent Skill Library Index (Deep Scan)

這是一份深度爬取的 AI Agent Skill 索引清單。

## 如何使用
1. 查找編號: 在下方表格找到您感興趣的 Skill 編號（ID）。
2. 下載研究: 執行 python skill_fetcher.py fetch [ID]
3. 更新索引: python skill_fetcher.py update

---

## Skill 索引清單

| ID | GitHub 帳號 | Skill 名稱 | 功能描述 | 來源 (Repo/Provider) |
| :--- | :--- | :--- | :--- | :--- |
| :--- | :--- | :--- | :--- | :--- |
"""
    rows = []
    for s in skills:
        desc = s['description'].replace("|", "\\|")
        desc = desc[:150] + "..." if len(desc) > 150 else desc
        rows.append(f"| {s['id']} | **{s['github_user']}** | [{s['name']}]({s['url']}) | {desc} | {s['source']} |")
    
    footer = f"\n\n---\n\n最後更新時間: {now} (實收項目: {len(skills)} 個)"
    return header + "\n".join(rows) + footer

def download_skill(skill_id):
    if not os.path.exists(DATA_FILE):
        print("錯誤: 找不到數據檔案，請先執行 update")
        return

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        skills = json.load(f)
    
    skill = next((s for s in skills if s['id'] == int(skill_id)), None)
    if not skill:
        print(f"錯誤: 找不到編號為 {skill_id} 的項目")
        return

    target_dir = os.path.join("downloads", re.sub(r'[\\/:*?"<>|]', '_', skill['name']))
    os.makedirs(target_dir, exist_ok=True)

    print(f"正在抓取 Skill: {skill['name']} 到 {target_dir}...")
    base_raw_url = github_to_raw(skill['url'])
    
    for filename in ["/SKILL.md", "/README.md", "/index.md", "/package.json"]:
        content = fetch_content(base_raw_url + filename)
        if content:
            local_path = os.path.join(target_dir, filename.lstrip("/"))
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  [+] 已下載: {filename}")
    
    print(f"完成！")

def update_index():
    print("[Deep Scan] 開始執行全量更新 (新增 GitHub 帳號欄位)...")
    main_content = fetch_content(SEED_URL)
    if not main_content:
        return

    skills = parse_main_readme(main_content)
    print(f"✅ 解析完成，共有 {len(skills)} 個唯一 Skill 條目。")

    print(f"🚀 開始對所有條目進行深度掃描...")
    scanned_count = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_skill = {executor.submit(extract_deep_info, s): s for s in skills}
        for future in as_completed(future_to_skill):
            scanned_count += 1
            if scanned_count % 50 == 0:
                print(f"⏳ 進度: {scanned_count}/{len(skills)}...")

    skills.sort(key=lambda x: x['id'])
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(skills, f, ensure_ascii=False, indent=2)

    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write(generate_markdown(skills))
    
    print(f"🎉 深度索引已重新生成至 {INDEX_FILE}")

def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "fetch" and len(sys.argv) > 2:
            download_skill(sys.argv[2])
        elif cmd == "update":
            update_index()
    else:
        update_index()

if __name__ == "__main__":
    main()
