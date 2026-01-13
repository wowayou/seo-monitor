import asyncio
import os
import re
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlparse, urljoin
import pandas as pd
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# ================= ⚙️ 全局配置 =================

# 关键词映射 (与 v4 保持一致)
KEYWORDS = {
    "Contact": ["contact", "lianxi", "联系", "support"],
    "About": ["about", "profile", "story", "guanyu", "company", "简介", "关于"],
    "FAQ": ["faq", "help", "question", "wenti", "常见问题"],
    "News": ["news", "blog", "press", "media", "insight", "article", "zixun", "dongtai", "journal", "资讯", "新闻", "动态"],
    "Product": ["product", "item", "shop", "store", "collection", "category", "solution", "service", "chanpin", "anli", "产品", "案例", "服务", "解决方案"],
    "Search": ["search", "sousuo", "搜索", "?s="]
}

# 忽略的资源后缀
IGNORED_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.doc', '.docx', 
    '.xls', '.xlsx', '.zip', '.rar', '.mp4', '.mp3', '.css', '.js', '.json', '.xml'
}

class CrawlerConfig:
    def __init__(self):
        self.input_file = ""
        self.output_file = "urls.xlsx"
        self.check_indexability = False  # 是否检查可索引性
        self.max_pages_per_site = 50     # 单个站点最大抓取数 (软限制)
        self.concurrency = 3             # 并发站点数
        self.headless = True             # 无头模式

# ================= 🕷️ 爬虫核心逻辑 =================

class SmartCrawler:
    def __init__(self, config, log_callback):
        self.cfg = config
        self.log = log_callback
        self.stop_signal = False

    def get_slug_identifier(self, url):
        """从URL获取唯一标识符(Slug)"""
        try:
            path = urlparse(str(url)).path.strip('/')
            if not path: return "home"
            slug = path.split('/')[-1]
            if (slug.isdigit() or len(slug) < 3) and '/' in path:
                slug = path.split('/')[-2] + '-' + slug
            if '.' in slug: slug = slug.rsplit('.', 1)[0]
            return slug[:30]
        except: return "unknown"

    def classify_page(self, url, title=""):
        """核心分类逻辑"""
        u = str(url).lower()
        t = str(title).lower()
        path = urlparse(u).path

        # 1. 首页
        if path in ["", "/", "/index.php", "/index.html", "/default.aspx"]:
            return "首页", None, 100

        # 2. 搜索页
        if any(k in u for k in KEYWORDS["Search"]):
            return "搜索页", None, 90

        # 3. 关于我们
        if any(k in u or k in t for k in KEYWORDS["About"]):
            return "关于我们", None, 90

        # 4. 联系我们
        if any(k in u or k in t for k in KEYWORDS["Contact"]):
            return "联系我们", None, 90

        # 5. FAQ
        if any(k in u or k in t for k in KEYWORDS["FAQ"]):
            return "FAQ", None, 90

        # 6. 新闻/博客
        if any(k in u for k in KEYWORDS["News"]):
            is_list = False
            if "category" in u or "tag" in u or "list" in u or path.endswith("/news/") or path.endswith("/blog/"):
                is_list = True
            elif len(path.strip("/").split("/")) <= 2: 
                is_list = True
            return "新闻", "聚合页" if is_list else "详情页", 80

        # 7. 产品/解决方案
        if any(k in u for k in KEYWORDS["Product"]):
            is_list = False
            if "category" in u or "collection" in u or "list" in u or path.endswith("/product/") or path.endswith("/products/"):
                is_list = True
            elif len(path.strip("/").split("/")) > 3: 
                is_list = False
            return "产品", "聚合页" if is_list else "详情页", 80

        return "其他", None, 0

    async def handle_age_gate(self, page):
        """处理年龄验证弹窗"""
        # 常见弹窗选择器
        selectors = [
            ".lay-btn .colsebtn1",   # 用户指定的
            "a.act.colsebtn1",       # 变体
            "button:has-text('21+')",
            "a:has-text('21+')",
            "button:has-text('I am 21')",
            "button:has-text('Yes')",
            "button:has-text('Enter Site')",
            "#age-gate-yes",
            ".age-gate-submit"
        ]
        
        for sel in selectors:
            try:
                if await page.locator(sel).is_visible(timeout=2000):
                    self.log(f"   🛡️ 检测到年龄弹窗，尝试点击: {sel}")
                    await page.locator(sel).click()
                    await asyncio.sleep(1) # 等待消失
                    return True
            except: pass
        return False

    async def is_indexable(self, page):
        """检查页面是否可索引"""
        try:
            # 1. 检查 meta robots
            meta_robots = await page.locator('meta[name="robots"]').get_attribute('content')
            if meta_robots and "noindex" in meta_robots.lower():
                return False
            
            # 2. 检查 title 是否包含 404
            title = await page.title()
            if "404" in title or "not found" in title.lower():
                return False
                
            return True
        except:
            return True # 默认放行

    async def crawl_site(self, context, start_url, project_name):
        """爬取单个站点"""
        domain = urlparse(start_url).netloc
        self.log(f"🌐 [{project_name}] 开始爬取: {start_url}")
        
        discovered_links = set()
        pools = {k: [] for k in ["首页", "关于我们", "联系我们", "FAQ", "搜索页", "新闻聚合页", "新闻详情页", "产品聚合页", "产品详情页", "产品分类页"]}
        
        page = await context.new_page()
        
        try:
            # 1. 访问首页
            try:
                await page.goto(start_url, timeout=40000, wait_until="domcontentloaded")
            except:
                self.log(f"⚠️ [{project_name}] 首页访问失败，重试...")
                await page.goto(start_url, timeout=60000, wait_until="load")

            # 2. 处理弹窗
            await self.handle_age_gate(page)
            
            # 3. 滚动加载
            for _ in range(3):
                await page.mouse.wheel(0, 1000)
                await asyncio.sleep(0.5)

            # 4. 获取首页所有链接
            hrefs = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a')).map(a => a.href)
            }""")
            
            # 5. 初步筛选与分类
            internal_links = []
            for href in hrefs:
                u = urlparse(href)
                # 必须是同域名
                if u.netloc == domain or not u.netloc:
                    # 排除静态资源
                    path = u.path.lower()
                    if any(path.endswith(ext) for ext in IGNORED_EXTENSIONS): continue
                    
                    full_url = urljoin(start_url, href)
                    full_url = full_url.split('#')[0].rstrip('/') # 去重hash和末尾斜杠
                    
                    if full_url not in discovered_links and full_url.startswith("http"):
                        discovered_links.add(full_url)
                        internal_links.append(full_url)
                        
                        # 立即分类
                        cat, sub, _ = self.classify_page(full_url)
                        if cat == "首页": pools["首页"].append(full_url)
                        elif cat == "关于我们": pools["关于我们"].append(full_url)
                        elif cat == "联系我们": pools["联系我们"].append(full_url)
                        elif cat == "FAQ": pools["FAQ"].append(full_url)
                        elif cat == "搜索页": pools["搜索页"].append(full_url)
                        elif cat == "新闻":
                            if sub == "聚合页": pools["新闻聚合页"].append(full_url)
                            else: pools["新闻详情页"].append(full_url)
                        elif cat == "产品":
                            if sub == "聚合页": 
                                if "category" in full_url: pools["产品分类页"].append(full_url)
                                else: pools["产品聚合页"].append(full_url)
                            else: pools["产品详情页"].append(full_url)

            self.log(f"   📊 [{project_name}] 首页发现 {len(internal_links)} 个链接")

            # 6. 二级深度搜索 (如果缺少关键页面)
            # 策略：如果缺少详情页，但有聚合页，去聚合页抓取
            
            async def quick_fetch_children(parent_url):
                self.log(f"   🔍 [{project_name}] 深入抓取: {parent_url}")
                try:
                    await page.goto(parent_url, timeout=30000, wait_until="domcontentloaded")
                    await self.handle_age_gate(page)
                    child_hrefs = await page.evaluate("""() => Array.from(document.querySelectorAll('a')).map(a => a.href)""")
                    new_found = 0
                    for h in child_hrefs:
                        fu = urljoin(start_url, h).split('#')[0].rstrip('/')
                        if fu not in discovered_links and domain in fu:
                             discovered_links.add(fu)
                             cat, sub, _ = self.classify_page(fu)
                             if cat == "产品" and sub == "详情页": pools["产品详情页"].append(fu)
                             elif cat == "新闻" and sub == "详情页": pools["新闻详情页"].append(fu)
                             new_found += 1
                    return new_found
                except: return 0

            # 补全产品详情
            if not pools["产品详情页"] and (pools["产品聚合页"] or pools["产品分类页"]):
                candidates = pools["产品分类页"] + pools["产品聚合页"]
                # 选最短的一个去抓
                if candidates:
                    target = sorted(candidates, key=len)[0]
                    await quick_fetch_children(target)

            # 补全新闻详情
            if not pools["新闻详情页"] and pools["新闻聚合页"]:
                target = sorted(pools["新闻聚合页"], key=len)[0]
                await quick_fetch_children(target)

            # 7. 生成候选列表 (Selection)
            final_candidates = []
            
            # 辅助函数：添加候选
            def add_candidate(pool_key, cat_name, type_name_tmpl, selection_strategy="shortest", limit=1):
                if not pools[pool_key]: return
                
                # 排序策略
                if selection_strategy == "shortest":
                    sorted_list = sorted(list(set(pools[pool_key])), key=lambda x: (len(x), x))
                else: # longest / median
                    sorted_list = sorted(list(set(pools[pool_key])), key=lambda x: (len(x), x))
                
                selected = []
                if selection_strategy == "median" and len(sorted_list) > 2:
                    mid = len(sorted_list) // 2
                    selected = [sorted_list[mid]]
                elif selection_strategy == "longest":
                    selected = [sorted_list[-1]]
                else: # shortest
                    selected = sorted_list[:limit]
                
                for url in selected:
                    # 确定 PageType 名称
                    if "单页" in type_name_tmpl or "分类页" in type_name_tmpl:
                        slug = self.get_slug_identifier(url)
                        p_type = f"{type_name_tmpl}-{slug}"
                    else:
                        p_type = type_name_tmpl
                        
                    final_candidates.append({
                        "Project": project_name,
                        "Category": cat_name,
                        "PageType": p_type,
                        "URL": url
                    })

            # 执行筛选
            if pools["首页"]: 
                final_candidates.append({"Project": project_name, "Category": "首页", "PageType": "首页", "URL": pools["首页"][0]})
            else:
                final_candidates.append({"Project": project_name, "Category": "首页", "PageType": "首页", "URL": start_url})

            add_candidate("关于我们", "关于我们", "关于我们")
            add_candidate("联系我们", "联系我们", "联系我们")
            add_candidate("FAQ", "FAQ", "FAQ")
            add_candidate("搜索页", "搜索页", "搜索页")
            
            add_candidate("新闻聚合页", "新闻", "新闻聚合页")
            add_candidate("新闻详情页", "新闻", "新闻单页", selection_strategy="longest") # 详情页通常长
            
            add_candidate("产品聚合页", "产品", "产品聚合页")
            add_candidate("产品分类页", "产品", "产品分类页")
            add_candidate("产品详情页", "产品", "产品单页", selection_strategy="median") # 选中等长度的

            # --- NEW: Check SEO Core Files ---
            self.log(f"   🤖 [{project_name}] 检查 SEO 核心文件...")
            
            # 1. 检查 robots.txt
            robots_url = urljoin(start_url, "/robots.txt")
            robots_content = ""
            try:
                resp_robots = await page.request.get(robots_url)
                if resp_robots.status == 200:
                    self.log(f"      ✅ 发现 Robots.txt: {robots_url}")
                    final_candidates.append({
                        "Project": project_name,
                        "Category": "SEO核心",
                        "PageType": "Robots.txt",
                        "URL": robots_url
                    })
                    # 尝试获取内容以解析 Sitemap
                    try:
                        robots_content = await resp_robots.text()
                    except: pass
                else:
                    self.log(f"      ⚠️ 未找到 Robots.txt (Status: {resp_robots.status})")
            except Exception as e:
                self.log(f"      ❌ 检查 Robots.txt 出错: {e}")

            # 2. 检查 Sitemap
            sitemap_found = False
            sitemap_candidates = []
            
            # 2.1 从 robots.txt 解析 (优先级最高)
            if robots_content:
                found_in_robots = re.findall(r'Sitemap:\s*(http[s]?://[^\s]+)', robots_content, re.IGNORECASE)
                for sm in found_in_robots:
                    sitemap_candidates.append(sm.strip())
            
            # 2.2 添加常见路径变体
            common_paths = [
                "/sitemap.xml",
                "/sitemap_index.xml", 
                "/sitemap-index.xml",
                "/wp-sitemap.xml",
                "/sitemap/sitemap.xml"
            ]
            for p in common_paths:
                sitemap_candidates.append(urljoin(start_url, p))
            
            # 去重并保持顺序
            unique_candidates = []
            for c in sitemap_candidates:
                if c not in unique_candidates: unique_candidates.append(c)
                
            # 2.3 依次探测
            self.log(f"      🔍 开始探测 Sitemap (共 {len(unique_candidates)} 个潜在路径)...")
            for sm_url in unique_candidates:
                try:
                    resp_sm = await page.request.get(sm_url)
                    if resp_sm.status == 200:
                        self.log(f"      ✅ 发现 Sitemap: {sm_url}")
                        final_candidates.append({
                            "Project": project_name,
                            "Category": "SEO核心",
                            "PageType": "Sitemap",
                            "URL": sm_url
                        })
                        sitemap_found = True
                        break # 找到一个能用的就行，避免重复添加干扰监控
                except: pass
            
            if not sitemap_found:
                self.log(f"      ⚠️ 警告: 未找到任何有效的 Sitemap! (已尝试 {len(unique_candidates)} 个路径)")
                # 即使没找到，也可以把 sitemap.xml 作为占位符加进去，或者就不加了以免监控报错？
                # 用户要求"防止静默失败"，这里已经打印了警告日志。
                # 也可以添加一个 "Sitemap-Missing" 的条目？暂时只记录日志。

            # 8. 可索引性检查 (Check Indexability)
            valid_results = []
            if self.cfg.check_indexability:
                self.log(f"   🕵️ [{project_name}] 正在检查 {len(final_candidates)} 个页面的可索引性...")
                for item in final_candidates:
                    if self.stop_signal: break
                    
                    # 跳过非 HTML 页面的检查
                    if item["Category"] == "SEO核心":
                        valid_results.append(item)
                        continue

                    try:
                        # 复用当前页面对象进行检查
                        await page.goto(item["URL"], timeout=20000, wait_until="domcontentloaded")
                        # 不需要等太久，只要能看到 meta 即可
                        is_ok = await self.is_indexable(page)
                        if is_ok:
                            valid_results.append(item)
                        else:
                            self.log(f"      🚫 跳过不可索引页面: {item['PageType']}")
                    except Exception as e:
                        # 访问出错也算通过吧，防止误杀
                        valid_results.append(item)
            else:
                valid_results = final_candidates

            return valid_results

        except Exception as e:
            self.log(f"❌ [{project_name}] 爬取异常: {e}")
            # 至少返回首页
            return [{"Project": project_name, "Category": "首页", "PageType": "首页", "URL": start_url}]
        finally:
            await page.close()

    async def run(self):
        self.log("🚀 启动智能爬虫任务...")
        
        # 1. 读取输入
        urls = []
        try:
            if self.cfg.input_file.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(self.cfg.input_file)
                # 尝试找 URL 列
                col = next((c for c in df.columns if 'url' in c.lower() or 'address' in c.lower()), df.columns[0])
                urls = df[col].dropna().astype(str).tolist()
            else:
                with open(self.cfg.input_file, 'r', encoding='utf-8') as f:
                    urls = [line.strip() for line in f if line.strip()]
        except Exception as e:
            self.log(f"❌ 读取文件失败: {e}")
            return

        self.log(f"📂 读取到 {len(urls)} 个目标站点")

        all_results = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.cfg.headless)
            
            # 限制并发
            semaphore = asyncio.Semaphore(self.cfg.concurrency)
            
            async def worker(url):
                if self.stop_signal: return
                async with semaphore:
                    # 提取项目名
                    parsed = urlparse(url)
                    if not parsed.scheme: url = "https://" + url
                    domain = urlparse(url).netloc.replace("www.", "")
                    project_name = domain.split('.')[0].capitalize()
                    
                    context = await browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    )
                    
                    try:
                        res = await self.crawl_site(context, url, project_name)
                        all_results.extend(res)
                    finally:
                        await context.close()

            tasks = [worker(u) for u in urls]
            await asyncio.gather(*tasks)
            await browser.close()

        if self.stop_signal:
            self.log("🛑 任务已停止")
        
        # 导出结果
        if all_results:
            df_out = pd.DataFrame(all_results)
            # 排序：Project -> Category
            df_out.sort_values(by=['Project', 'Category'], inplace=True)
            df_out = df_out[['Project', 'Category', 'PageType', 'URL']]
            
            df_out.to_excel(self.cfg.output_file, index=False)
            self.log(f"\n✨ 任务完成！生成结果: {self.cfg.output_file}")
            self.log(f"📊 总计获取 {len(df_out)} 条监控规则")
            try:
                os.startfile(self.cfg.output_file)
            except: pass
        else:
            self.log("⚠️ 未获取到任何有效数据")

# ================= 🖥️ GUI 界面 =================

class CrawlerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SEO 智能URL获取工具 v5.0 (Crawler版)")
        self.root.geometry("600x550")
        
        self.input_path = tk.StringVar()
        self.check_idx = tk.BooleanVar(value=True) # 默认开启索引检查
        self.headless_mode = tk.BooleanVar(value=True)
        
        self.crawler = None
        self._create_widgets()

    def _create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        ttk.Label(main_frame, text="🕷️ 网站URL智能抓取生成器", font=('Microsoft YaHei', 14, 'bold')).pack(pady=(0, 20))
        
        # 1. 输入文件
        frame1 = ttk.LabelFrame(main_frame, text="1. 输入文件 (Txt/Excel - 仅含首页URL)", padding=10)
        frame1.pack(fill=tk.X, pady=5)
        ttk.Entry(frame1, textvariable=self.input_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(frame1, text="浏览...", command=self.browse_input).pack(side=tk.RIGHT)
        
        # 2. 选项
        frame2 = ttk.LabelFrame(main_frame, text="2. 抓取选项", padding=10)
        frame2.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(frame2, text="仅筛选可索引页面 (Check Indexable)", variable=self.check_idx).grid(row=0, column=0, sticky=tk.W, padx=10)
        ttk.Label(frame2, text="ℹ️ 开启后会自动过滤 noindex 和 404 页面，但速度会变慢").grid(row=1, column=0, sticky=tk.W, padx=10, pady=(2,0))
        
        ttk.Checkbutton(frame2, text="后台静默运行 (Headless)", variable=self.headless_mode).grid(row=2, column=0, sticky=tk.W, padx=10, pady=(10,0))
        
        # 3. 日志
        ttk.Label(main_frame, text="运行日志:").pack(anchor=tk.W, pady=(10, 0))
        self.log_text = tk.Text(main_frame, height=12, font=('Consolas', 9), state='disabled')
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        self.start_btn = ttk.Button(btn_frame, text="开始抓取", command=self.start)
        self.start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        ttk.Button(btn_frame, text="停止", command=self.stop).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=5)

    def browse_input(self):
        f = filedialog.askopenfilename(filetypes=[("Data Files", "*.txt;*.xlsx;*.xls")])
        if f: self.input_path.set(f)

    def log(self, msg):
        def _update():
            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, str(msg) + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state='disabled')
        self.root.after(0, _update)

    def start(self):
        if not self.input_path.get():
            messagebox.showerror("错误", "请先选择输入文件！")
            return
            
        self.start_btn.config(state='disabled')
        
        cfg = CrawlerConfig()
        cfg.input_file = self.input_path.get()
        cfg.check_indexability = self.check_idx.get()
        cfg.headless = self.headless_mode.get()
        
        self.crawler = SmartCrawler(cfg, self.log)
        
        thread = threading.Thread(target=self.run_async, args=(self.crawler,), daemon=True)
        thread.start()

    def stop(self):
        if self.crawler:
            self.crawler.stop_signal = True
            self.log("🛑 正在停止...")

    def run_async(self, crawler):
        asyncio.run(crawler.run())
        self.root.after(0, lambda: self.start_btn.config(state='normal'))

def main():
    root = tk.Tk()
    app = CrawlerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
