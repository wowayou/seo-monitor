import asyncio
import os
import time
import pandas as pd
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

try:
    from tqdm.asyncio import tqdm_asyncio
except ImportError:
    tqdm_asyncio = None

# ================= 配置区 (根据你的网络情况调整) =================

# 1. 严格加载开关 (True = 等待所有圈圈转完; False = 骨架出来就行)
STRICT_LOAD_MODE = True  

# 2. 网络重试设置 (对抗国外服务器不稳定的关键)
MAX_RETRIES = 2  # 如果失败，自动重试 2 次 (共尝试 3 次)

# 3. 基础设置
EXCEL_PATH = "urls.xlsx"
OUTPUT_ROOT = r"C:\Users\xhl\Desktop\SEO_Monitor_Data"
CONCURRENT_TASKS = 2      # ⚠️ 网络差时，强烈建议把并发降到 2 或 1，避免带宽挤兑
PAGE_TIMEOUT = 90000      # ⚠️ 针对国外服务器，超时延长至 90秒
VIEWPORT_SIZE = {'width': 1440, 'height': 900}

# 4. 黑名单 (加快速度，防止污染数据)
BLOCK_DOMAINS = [
    "google-analytics.com", "googletagmanager.com", "hm.baidu.com", "cnzz.com",
    "facebook.net", "connect.facebook.net", "doubleclick.net", "googleadservices.com"
]

# =============================================================

async def slow_scroll_down(page):
    """模拟平滑滚动，带熔断机制"""
    try:
        last_height = await page.evaluate("document.body.scrollHeight")
        scroll_count = 0
        max_scrolls = 30 

        while scroll_count < max_scrolls:
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(1.5) # 稍微多等一下图片加载
            
            new_height = await page.evaluate("document.body.scrollHeight")
            current_scroll_y = await page.evaluate("window.scrollY + window.innerHeight")
            scroll_count += 1
            
            if new_height == last_height or current_scroll_y >= new_height:
                # 到底了，再最后等一下确保懒加载触发
                await asyncio.sleep(2) 
                break
            last_height = new_height
    except Exception:
        pass # 滚动报错不应该打断主流程

async def capture_task(browser, row, semaphore):
    async with semaphore:
        project = row['Project']
        page_type = row['PageType']
        url = row['URL']
        
        task_result = {
            "Project": project,
            "PageType": page_type,
            "URL": url,
            "Status": "Pending",
            "LoadTime_s": 0.0,
            "RetryCount": 0,
            "ErrorMessage": ""
        }

        today_str = datetime.now().strftime("%Y-%m-%d")
        save_dir = os.path.join(OUTPUT_ROOT, today_str, project)
        filename = f"{page_type}.png"
        save_path = os.path.join(save_dir, filename)
        os.makedirs(save_dir, exist_ok=True)

        context = await browser.new_context(
            viewport=VIEWPORT_SIZE,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            ignore_https_errors=True
        )
        page = await context.new_page()

        # 路由拦截
        for pattern in BLOCK_DOMAINS:
            await page.route(f"**/*{pattern}*", lambda route: route.abort())

        total_start = time.time()
        
        # --- 重试循环逻辑 ---
        for attempt in range(MAX_RETRIES + 1):
            try:
                task_result["RetryCount"] = attempt
                if attempt > 0:
                    print(f"   [🔄 第{attempt}次重试] {project}-{page_type}...")

                load_start = time.time()

                # --- 核心策略：根据开关选择等待方式 ---
                if STRICT_LOAD_MODE:
                    # 严格模式：等待网络空闲 (至少500ms没请求)，适合由于图片多导致的慢
                    await page.goto(url, timeout=PAGE_TIMEOUT, wait_until="networkidle")
                else:
                    # 快速模式：DOM出来就行
                    await page.goto(url, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")
                
                load_duration = time.time() - load_start
                task_result["LoadTime_s"] = round(load_duration, 2)

                # 滚动加载
                await asyncio.wait_for(slow_scroll_down(page), timeout=60)

                # 如果是严格模式，滚动完再强制等待一下 "load" 事件，确保万无一失
                if STRICT_LOAD_MODE:
                     try:
                        # 尝试等待最终的 load 事件，如果已经触发过会直接通过
                        await page.wait_for_load_state("load", timeout=5000)
                     except:
                        pass # 就算超时也不要紧，刚才已经 networkidle 了

                # 截图
                await page.screenshot(path=save_path, full_page=True, timeout=30000)
                
                task_result["Status"] = "Success"
                print(f"[✅ 成功] {project}-{page_type} (耗时:{task_result['LoadTime_s']}s)")
                
                # 成功了就跳出循环，不再重试
                break 

            except Exception as e:
                error_msg = str(e).splitlines()[0]
                # 如果是最后一次尝试，才标记为失败
                if attempt == MAX_RETRIES:
                    task_result["Status"] = "Failed"
                    task_result["ErrorMessage"] = error_msg
                    print(f"[❌ 最终失败] {project}-{page_type}: {error_msg}")
                    with open(os.path.join(save_dir, f"ERROR_{page_type}.txt"), "w") as f:
                        f.write(f"URL: {url}\nError: {str(e)}")
                else:
                    # 如果不是最后一次，暂停一下再试
                    await asyncio.sleep(3) 

        await context.close()
        return task_result

async def main():
    if not os.path.exists(EXCEL_PATH):
        print(f"错误：找不到 {EXCEL_PATH}")
        return

    df = pd.read_excel(EXCEL_PATH).dropna(subset=['URL'])
    mode_str = "严格模式(等待资源全加载)" if STRICT_LOAD_MODE else "极速模式(只等骨架)"
    print(f"准备巡检 {len(df)} 个页面 | 模式: {mode_str} | 重试次数: {MAX_RETRIES}")
    
    semaphore = asyncio.Semaphore(CONCURRENT_TASKS)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        
        tasks = []
        for _, row in df.iterrows():
            tasks.append(capture_task(browser, row, semaphore))

        if tqdm_asyncio:
            results = await tqdm_asyncio.gather(*tasks, desc="任务进度")
        else:
            results = await asyncio.gather(*tasks)
            
        await browser.close()

    # 生成报告
    today_str = datetime.now().strftime("%Y-%m-%d")
    report_df = pd.DataFrame(results)
    
    # 整理列
    cols = ["Project", "PageType", "Status", "LoadTime_s", "RetryCount", "URL", "ErrorMessage", "ScreenshotPath"]
    for col in cols:
        if col not in report_df.columns: report_df[col] = ""
    report_df = report_df[cols]
    
    report_path = os.path.join(OUTPUT_ROOT, today_str, "inspection_report.xlsx")
    try:
        report_df.to_excel(report_path, index=False)
        print(f"\n📄 报告已生成: {report_path}")
    except:
        print(f"\n⚠️ 报告生成失败，请检查文件占用")

if __name__ == "__main__":
    start_time = datetime.now()
    asyncio.run(main())
    print(f"总耗时: {datetime.now() - start_time}")