import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import urllib3
from tqdm import tqdm
import time
import sys

# 解决requests请求出现的InsecureRequestWarning错误
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 定义颜色
GREEN, RED, YELLOW, RESET = "\033[92m", "\033[91m", "\033[93m", "\033[0m"

def extract_domains(text):
    """精准域名提取函数"""
    return list(set(re.findall(r'(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})*)', text)))

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
        pass
    return None

def query_baidu_weight(domains):
    """通过新接口查询百度权重和移动权重"""
    api_url = "https://apistore.aizhan.com/baidurank/siteinfos/**************"
    try:
        response = requests.get(api_url, params={"domains": "|".join(domains)}, timeout=10, verify=False)
        if response.status_code == 200 and response.json().get("code") == 200000:
            return response.json()["data"]["success"]
    except Exception:
        pass
    return []

def check_baidu_shoulu(domain):
    """检查百度收录数量"""
    try:
        response = requests.get(f"https://api.pearktrue.cn/api/website/shoulu.php?url={domain}", timeout=10)
        if response.status_code == 200 and response.json().get("code") == 200:
            return response.json()["data"].get("baidu", "未收录")
    except Exception:
        pass
    return "未收录"

def process_urls():
    input_file, output_file, alive_file = "urls.txt", "results.csv", "alive.txt"
    
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            domains = extract_domains(f.read())
    except FileNotFoundError:
        print(f"{RED}[-] 错误：未找到文件 {input_file}{RESET}")
        return
    
    print(f"[+] 待检测域名总数：{len(domains)}")
    
    # 初始化 CSV 文件并写入表头
    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        csv.writer(csvfile).writerow(["查询域名", "百度权重", "移动权重", "预计来路", "PC预计来路", "移动预计来路", "百度收录数量"])
    
    group_size = 50
    total_groups = (len(domains) + group_size - 1) // group_size
    
    try:
        with ThreadPoolExecutor(max_workers=20) as pool, open(alive_file, "w", encoding="utf-8") as alive_file_handle:
            alive_domains_buffer = []
            
            for i in range(0, len(domains), group_size):
                current_group = domains[i:i + group_size]
                
                # 存活探测
                with tqdm(total=len(current_group), desc=f"存活探测进度 (组 {i // group_size + 1}/{total_groups})", leave=False) as pbar:
                    futures = [pool.submit(check_domain_alive, domain) for domain in current_group]
                    for future in as_completed(futures):
                        result = future.result()
                        if result:
                            alive_domains_buffer.append(result)
                            alive_file_handle.write(f"{result}\n")
                        pbar.update(1)
                
                # 权重查询
                while len(alive_domains_buffer) >= group_size:
                    weight_group = alive_domains_buffer[:group_size]
                    alive_domains_buffer = alive_domains_buffer[group_size:]
                    
                    # 淡黄色进度条：权重查询
                    with tqdm(total=len(weight_group), desc=f"{YELLOW}权重查询进度{RESET}", leave=False, colour="yellow") as pbar:
                        weight_results = query_baidu_weight(weight_group) or [
                            {"domain": domain, "pc_br": "未找到", "m_br": "未找到", "ip": "未找到",
                             "pc_ip": "未找到", "m_ip": "未找到"} for domain in weight_group]
                        pbar.update(len(weight_group))
                    
                    # 淡黄色进度条：收录查询
                    with tqdm(total=len(weight_results), desc=f"{YELLOW}收录查询进度{RESET}", leave=False, colour="yellow") as pbar:
                        shoulu_futures = {pool.submit(check_baidu_shoulu, r["domain"]): r for r in weight_results}
                        results_to_save = []
                        for future in as_completed(shoulu_futures):
                            r = shoulu_futures[future]
                            r["baidu_shoulu"] = future.result()
                            results_to_save.append(r)
                            pbar.update(1)
                    
                    with open(output_file, "a", newline="", encoding="utf-8") as csvfile:
                        writer = csv.writer(csvfile)
                        for r in results_to_save:
                            writer.writerow([
                                r["domain"], r["pc_br"], r["m_br"], r["ip"],
                                r["pc_ip"], r["m_ip"], r["baidu_shoulu"]
                            ])
                    
                    time.sleep(3)
            
            # 处理剩余域名
            if alive_domains_buffer:
                for domain in alive_domains_buffer:
                    # 淡黄色进度条：单个域名权重查询
                    with tqdm(total=1, desc=f"{YELLOW}权重查询进度{RESET}", leave=False, colour="yellow") as pbar:
                        single_result = query_baidu_weight([domain]) or [{
                            "domain": domain, "pc_br": "未找到", "m_br": "未找到", "ip": "未找到",
                            "pc_ip": "未找到", "m_ip": "未找到"
                        }]
                        pbar.update(1)
                    
                    # 淡黄色进度条：单个域名收录查询
                    with tqdm(total=1, desc=f"{YELLOW}收录查询进度{RESET}", leave=False, colour="yellow") as pbar:
                        shoulu = check_baidu_shoulu(domain)
                        single_result[0]["baidu_shoulu"] = shoulu
                        pbar.update(1)
                    
                    with open(output_file, "a", newline="", encoding="utf-8") as csvfile:
                        writer = csv.writer(csvfile)
                        writer.writerow([
                            single_result[0]["domain"], single_result[0]["pc_br"], single_result[0]["m_br"],
                            single_result[0]["ip"], single_result[0]["pc_ip"], single_result[0]["m_ip"],
                            single_result[0]["baidu_shoulu"]
                        ])
                    time.sleep(3)
    
    except KeyboardInterrupt:
        print(f"\n{RED}[!] 用户中断：已强行退出脚本。{RESET}")
        sys.exit(0)
    
    print(f"\n[+] 结果已保存到 {output_file}")
    print(f"[+] 存活域名已保存到 {alive_file}")

if __name__ == '__main__':
    process_urls()
