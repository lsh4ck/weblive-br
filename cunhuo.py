import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import urllib3
from tqdm import tqdm
import time

# 解决requests请求出现的InsecureRequestWarning错误
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 定义颜色
GREEN = "\033[92m"  # 绿色
RED = "\033[91m"    # 红色
RESET = "\033[0m"   # 重置颜色

def extract_domains(text):
    """精准域名提取函数"""
    pattern = r'(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})*)'
    return list(set(re.findall(pattern, text)))

def check_domain_alive(domain):
    """检查域名是否存活（状态码为200）"""
    try:
        for protocol in ["http", "https"]:
            response = requests.head(f"{protocol}://{domain}", timeout=10, verify=False, allow_redirects=True)
            if response.status_code == 200:
                print(f"{GREEN}[+] 域名存活: {domain}{RESET}")
                return domain
        print(f"{RED}[-] 域名不可用: {domain}{RESET}")
    except Exception:
        print(f"{RED}[-] 域名不可用: {domain}{RESET}")
    return None

def query_baidu_weight(domains):
    """通过新接口查询百度权重和移动权重"""
    api_url = "https://apistore.aizhan.com/baidurank/siteinfos/*****************"
    try:
        response = requests.get(api_url, params={"domains": "|".join(domains)}, timeout=10, verify=False)
        if response.status_code == 200 and response.json().get("code") == 200000:
            return response.json()["data"]["success"]
        print(f"{RED}[-] 权重查询失败: {response.json().get('msg', '未知错误')}{RESET}")
    except Exception as e:
        print(f"{RED}[-] 权重查询失败: {e}{RESET}")
    return []

def check_baidu_shoulu(domain):
    """检查百度收录数量"""
    api_url = f"https://api.pearktrue.cn/api/website/shoulu.php?url={domain}"
    try:
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200 and response.json().get("code") == 200:
            return response.json()["data"].get("baidu", "未收录")
    except Exception:
        pass
    return "未收录"

def update_csv_with_shoulu(file_path, domain, shoulu):
    """更新CSV文件中的收录信息"""
    try:
        with open(file_path, "r", newline="", encoding="utf-8") as csvfile:
            rows = list(csv.reader(csvfile))
        with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(rows[0])  # 写入表头
            for row in rows[1:]:
                if row[0] == domain:
                    row[-1] = shoulu
                writer.writerow(row)
    except Exception as e:
        print(f"{RED}[-] 更新CSV文件时出错: {e}{RESET}")

def process_urls():
    input_file = "urls.txt"
    output_file = "results.csv"
    
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            domains = extract_domains(f.read())
    except FileNotFoundError:
        print(f"{RED}[-] 错误：未找到文件 {input_file}，请确保文件存在且位于脚本同目录下。{RESET}")
        return
    
    print(f"[+] 待检测域名总数：{len(domains)}")
    
    # 存活探测
    alive_domains = []
    with ThreadPoolExecutor(max_workers=10) as pool, tqdm(total=len(domains), desc="存活探测进度") as pbar:
        futures = [pool.submit(check_domain_alive, domain) for domain in domains]
        for future in as_completed(futures):
            result = future.result()
            if result:
                alive_domains.append(result)
            pbar.update(1)
    
    print(f"\n[+] 存活域名数量: {len(alive_domains)}")
    if not alive_domains:
        print(f"{RED}[-] 没有存活域名，无需继续查询。{RESET}")
        return
    
    # 初始化 CSV 文件并写入表头
    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["查询域名", "百度权重", "移动权重", "预计来路", "PC预计来路", "移动预计来路", "百度收录数量"])
    
    # 权重查询（每组 50 个域名，间隔 2 秒）
    group_size = 50
    with tqdm(total=len(alive_domains), desc="权重查询进度") as pbar:
        for i in range(0, len(alive_domains), group_size):
            group = alive_domains[i:i + group_size]
            weight_results = query_baidu_weight(group)
            if weight_results:
                with open(output_file, "a", newline="", encoding="utf-8") as csvfile:
                    writer = csv.writer(csvfile)
                    for result in weight_results:
                        writer.writerow([
                            result.get("domain", "未找到"),
                            result.get("pc_br", "未找到"),
                            result.get("m_br", "未找到"),
                            result.get("ip", "未找到"),
                            result.get("pc_ip", "未找到"),
                            result.get("m_ip", "未找到"),
                            "暂无"
                        ])
            pbar.update(len(group))
            if i + group_size < len(alive_domains):
                time.sleep(2)
    
    # 收录查询（并发处理）
    with ThreadPoolExecutor(max_workers=10) as pool, tqdm(total=len(alive_domains), desc="收录查询进度") as pbar:
        futures = {pool.submit(check_baidu_shoulu, domain): domain for domain in alive_domains}
        for future in as_completed(futures):
            domain = futures[future]
            shoulu = future.result()
            update_csv_with_shoulu(output_file, domain, shoulu)
            pbar.update(1)
    
    print(f"\n[+] 结果已保存到 {output_file}")

if __name__ == '__main__':
    process_urls()
