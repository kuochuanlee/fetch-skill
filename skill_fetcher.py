import urllib.request
import re
import os
import ssl
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 設定種子 URL
SEED_URL = "https://raw.githubusercontent.com/VoltAgent/awesome-agent-skills/main/README.md"
INDEX_FILE = "skill-index.md"
MAX_WORKERS = 10  # 並行抓取數量

def get_ssl_context():
    # 使用 os.path.expanduser() 動態取得使用者目錄
    user_home = os.path.expanduser('~')
    cert_path = os.path.join(user_home, '.python-certs', 'cacert.pem')
    context = ssl.create_default_context()
    if os.path.exists(cert_path):
        context.load_verify_locations(cafile=cert_path)
    return context

def github_to_raw(url):
    """
    將 GitHub 網頁 URL 轉換為 Raw 內容 URL
    """
    raw_url = url.replace("github.com", "raw.githubusercontent.com")
    raw_url = raw_url.replace("/blob/", "/")
    raw_url = raw_url.replace("/tree/", "/")
    # 移除尾部的斜線
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
    """
    深度掃描單個 Skill 的內容
    """
    base_raw_url = github_to_raw(skill['url'])
    
    # 嘗試尋找 SKILL.md 或 README.md
    for filename in ["/SKILL.md", "/README.md", "/index.md"]:
        content = fetch_content(base_raw_url + filename)
        if content:
            # 提取第一個 H1 標題作為正確名稱
            title_match = re.search(r'^#\s+(.*)', content, re.M)
            if title_match:
                skill['name'] = title_match.group(1).strip()
            
            # 提取功能簡介 (通常是標題後的第 1-2 段)
            features_match = re.search(r'##\s+(?:Features|Functions|Tools|功能)(.*?)(?=##|$)', content, re.S | re.I)
            if features_match:
                desc = features_match.group(1).strip()
                # 清理 Markdown 格式
                desc = re.sub(r'[\r\n]+', ' ', desc)
                desc = re.sub(r'[*#>`-]', '', desc)
                skill['description'] = desc[:200] + "..." if len(desc) > 200 else desc
            
            skill['deep_scanned'] = True
            break
    return skill

def parse_main_readme(content):
    skills = []
    pattern = r'\[(.*?)\]\((https?://github\.com/.*?)\)\s*[-:]?\s*(.*)'
    matches = re.finditer(pattern, content)
    
    for match in matches:
        url = match.group(2).strip()
        if any(x in url.lower() for x in ["badge", "voltagent/awesome-agent-skills", "img.shields.io"]):
            continue
            
        skills.append({
            "name": match.group(1).strip(),
            "url": url,
            "description": re.sub(r'<.*?>', '', match.group(3)).strip(),
            "source": url.split("/")[-2] + "/" + url.split("/")[-1],
            "category": "General",
            "tags": "#AI #Skill",
            "deep_scanned": False
        })
    return skills

def generate_markdown(skills):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"""# AI Agent Skill Library Index (Deep Scan)

這是一份深度爬取的 AI Agent Skill 索引清單。

## 如何使用
1. 關鍵字查找: 使用 Ctrl + F。
2. 自動更新: python skill_fetcher.py

---

## Skill 索引清單

| Skill 名稱 | 功能描述 | 來源 (Repo/Provider) | 類別 | 標籤 |
| :--- | :--- | :--- | :--- | :--- |
"""
    rows = []
    for s in skills:
        desc = s['description'].replace("|", "\\|")
        rows.append(f"| [{s['name']}]({s['url']}) | {desc} | {s['source']} | {s['category']} | {s['tags']} |")
    
    footer = f"\n\n---\n\n最後更新時間: {now} (共計 {len(skills)} 個項目)"
    return header + "\n".join(rows) + footer

def main():
    print("[Deep Scan] 開始執行...")
    main_content = fetch_content(SEED_URL)
    if not main_content:
        return

    initial_skills = parse_main_readme(main_content)
    target_skills = initial_skills 
    
    print(f"成功找到 {len(initial_skills)} 個來源，準備對所有項目進行深度掃描...")

    scanned_skills = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_skill = {executor.submit(extract_deep_info, s): s for s in target_skills}
        for i, future in enumerate(as_completed(future_to_skill)):
            try:
                result = future.result()
                scanned_skills.append(result)
                if i % 5 == 0:
                    print(f"已掃描 {i}/{len(target_skills)} 個項目...")
            except Exception as e:
                print(f"掃描失敗: {e}")

    final_skills = scanned_skills + initial_skills[50:]
    
    md_content = generate_markdown(final_skills)
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write(md_content)
    
    print(f"深度索引已成功寫入 {INDEX_FILE}")

if __name__ == "__main__":
    main()
