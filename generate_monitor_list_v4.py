import pandas as pd
import os
import re
from urllib.parse import urlparse
import tkinter as tk
from tkinter import filedialog

# --- 配置 ---
DEFAULT_INPUT_FILE = "crawl_result.xlsx"
OUTPUT_FILE = "urls.xlsx"

# 关键词映射 (可根据需求扩展)
KEYWORDS = {
    "Contact": ["contact", "lianxi", "联系", "support"],
    "About": ["about", "profile", "story", "guanyu", "company", "简介", "关于"],
    "FAQ": ["faq", "help", "question", "wenti", "常见问题"],
    "News": ["news", "blog", "press", "media", "insight", "article", "zixun", "dongtai", "journal", "资讯", "新闻", "动态"],
    "Product": ["product", "item", "shop", "store", "collection", "category", "solution", "service", "chanpin", "anli", "产品", "案例", "服务", "解决方案"],
    "Search": ["search", "sousuo", "搜索", "?s="]
}

def select_file():
    """弹出文件选择框"""
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(
        title="选择 Screaming Frog 导出的 Excel/CSV 文件",
        filetypes=[("Excel Files", "*.xlsx;*.xls"), ("CSV Files", "*.csv")]
    )
    return file_path

def get_domain_project(url, title=None):
    """从URL提取项目名，尝试从标题提取品牌名"""
    try:
        parsed = urlparse(str(url))
        domain = parsed.netloc
        if domain.startswith("www."):
            domain = domain[4:]
        
        # 尝试从标题提取品牌 (通常在 - 或 | 之后)
        project_name = domain
        if title and isinstance(title, str):
            separators = ['-', '|', '_', '—']
            for sep in separators:
                if sep in title:
                    candidate = title.split(sep)[-1].strip()
                    # 品牌名通常不长
                    if 1 < len(candidate) < 20:
                        project_name = candidate
                        break
        return project_name
    except:
        return "Unknown"

def classify_page(url, title, h1):
    """
    核心分类逻辑
    返回: (Category, SubType, Score)
    Category: Product, News, About, Contact, Home, Other
    SubType: List, Detail, None
    """
    u = str(url).lower()
    t = str(title).lower() if pd.notna(title) else ""
    h = str(h1).lower() if pd.notna(h1) else ""
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
        # 判断是列表还是详情
        # 列表特征: 路径短, 包含 category, tag, list
        # 详情特征: 路径长, 包含 .html, 日期, 具体文章名
        
        is_list = False
        if "category" in u or "tag" in u or "list" in u or path.endswith("/news/") or path.endswith("/blog/"):
            is_list = True
        elif len(path.strip("/").split("/")) <= 2: # 路径很浅可能是列表
            is_list = True
            
        return "新闻", "聚合页" if is_list else "详情页", 80

    # 7. 产品/解决方案
    if any(k in u for k in KEYWORDS["Product"]):
        is_list = False
        if "category" in u or "collection" in u or "list" in u or path.endswith("/product/") or path.endswith("/products/"):
            is_list = True
        # 排除可能是详情的情况
        elif len(path.strip("/").split("/")) > 3: 
            is_list = False
            
        return "产品", "聚合页" if is_list else "详情页", 80

    return "其他", None, 0

def get_slug_identifier(url):
    """从URL获取唯一标识符(Slug)，用于生成稳定的文件名"""
    try:
        path = urlparse(str(url)).path.strip('/')
        if not path: return "home"
        
        # 获取最后一段
        slug = path.split('/')[-1]
        
        # 如果最后一段是数字或太短，取前一段
        if (slug.isdigit() or len(slug) < 3) and '/' in path:
             slug = path.split('/')[-2] + '-' + slug
             
        # 去除扩展名
        if '.' in slug:
            slug = slug.rsplit('.', 1)[0]
            
        return slug[:30] # 限制长度
    except:
        return "unknown"

def main():
    print("🚀 启动 URL 智能分类工具...")
    
    # 1. 获取文件
    input_file = select_file()
    if not input_file:
        print("❌ 未选择文件，程序退出")
        return

    print(f"📂 正在读取: {input_file}")
    
    try:
        if input_file.endswith('.csv'):
            df = pd.read_csv(input_file)
        else:
            df = pd.read_excel(input_file)
    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        return

    # 2. 规范化列名
    df.columns = df.columns.str.strip()
    
    # 寻找关键列
    url_col = next((c for c in ['Address', 'URL', 'Original Url'] if c in df.columns), None)
    status_col = next((c for c in ['Status Code', 'Status'] if c in df.columns), None)
    title_col = next((c for c in ['Title 1', 'Title'] if c in df.columns), None)
    h1_col = next((c for c in ['H1-1', 'H1'] if c in df.columns), None)
    content_type_col = next((c for c in ['Content Type'] if c in df.columns), None)

    if not url_col:
        print("❌ 无法找到 URL 列 (Address/URL)")
        return

    print(f"✅ 找到关键列: URL='{url_col}', Title='{title_col}', Status='{status_col}'")

    # 3. 预处理
    # 过滤非 200
    if status_col:
        df = df[df[status_col] == 200]
    
    # 过滤非 HTML
    if content_type_col:
        df = df[df[content_type_col].astype(str).str.contains("html", case=False, na=False)]

    # 提取项目名 (基于域名)
    df['Domain_Project'] = df[url_col].apply(lambda x: get_domain_project(x))
    
    # 进一步优化项目名：如果同一域名下 Title 后缀一致，则使用 Title 后缀
    # 这里简单处理：直接使用 apply 结合 title
    if title_col:
        df['Project_Name'] = df.apply(lambda row: get_domain_project(row[url_col], row[title_col]), axis=1)
    else:
        df['Project_Name'] = df['Domain_Project']

    final_rows = []
    
    # 4. 按项目分组处理
    grouped = df.groupby('Domain_Project') # 还是按域名分组最稳妥
    
    print(f"🔍 识别到 {len(grouped)} 个网站项目，开始分类...")

    for domain, group in grouped:
        # 获取该组最常用的 Project Name (众数)
        project_name = group['Project_Name'].mode()[0] if not group['Project_Name'].empty else domain
        print(f"   - 处理: {project_name} ({domain}) | 页面数: {len(group)}")
        
        # 分类容器
        pools = {
            "首页": [],
            "关于我们": [],
            "联系我们": [],
            "FAQ": [],
            "搜索页": [],
            "新闻聚合页": [],
            "新闻详情页": [],
            "产品聚合页": [],
            "产品详情页": [],
            "产品分类页": [] # 额外区分
        }

        for _, row in group.iterrows():
            url = row[url_col]
            title = row[title_col] if title_col else ""
            h1 = row[h1_col] if h1_col else ""
            
            cat, sub, score = classify_page(url, title, h1)
            
            if cat == "首页":
                pools["首页"].append(url)
            elif cat == "关于我们":
                pools["关于我们"].append(url)
            elif cat == "联系我们":
                pools["联系我们"].append(url)
            elif cat == "FAQ":
                pools["FAQ"].append(url)
            elif cat == "搜索页":
                pools["搜索页"].append(url)
            elif cat == "新闻":
                if sub == "聚合页": pools["新闻聚合页"].append(url)
                else: pools["新闻详情页"].append(url)
            elif cat == "产品":
                if sub == "聚合页": 
                    # 细分：如果URL包含 category 可能是分类页，否则是总聚合
                    if "category" in str(url):
                        pools["产品分类页"].append(url)
                    else:
                        pools["产品聚合页"].append(url)
                else: 
                    pools["产品详情页"].append(url)

        # 5. 抽样逻辑 (Selection)
        # 使用 (len(x), x) 排序确保确定性：优先短路径，长度相同时按字母序
        
        # 首页: 必选
        if pools["首页"]:
            final_rows.append({
                "Project": project_name, 
                "Category": "首页",
                "PageType": "首页", 
                "URL": pools["首页"][0]
            })
        
        # 功能页: 选路径最短的
        for p_type in ["关于我们", "联系我们", "FAQ", "搜索页"]:
            if pools[p_type]:
                best_url = sorted(pools[p_type], key=lambda x: (len(x), x))[0]
                final_rows.append({
                    "Project": project_name, 
                    "Category": p_type,
                    "PageType": p_type, 
                    "URL": best_url
                })

        # 新闻: 
        if pools["新闻聚合页"]:
            # 最短的作为聚合
            best_url = sorted(pools["新闻聚合页"], key=lambda x: (len(x), x))[0]
            final_rows.append({
                "Project": project_name, 
                "Category": "新闻",
                "PageType": "新闻聚合页", 
                "URL": best_url
            })
        
        if pools["新闻详情页"]:
            # 选一个长度适中的，或者最新的 (如果有日期)
            # 这里简单选最长的，通常详情页URL较长
            sorted_news = sorted(pools["新闻详情页"], key=lambda x: (len(x), x))
            best_detail = sorted_news[-1] if len(sorted_news) > 0 else sorted_news[0]
            
            # 生成唯一标识
            slug = get_slug_identifier(best_detail)
            final_rows.append({
                "Project": project_name, 
                "Category": "新闻",
                "PageType": f"新闻单页-{slug}", 
                "URL": best_detail
            })

        # 产品:
        # 1. 聚合页 (Root)
        if pools["产品聚合页"]:
             best_url = sorted(pools["产品聚合页"], key=lambda x: (len(x), x))[0]
             final_rows.append({
                 "Project": project_name, 
                 "Category": "产品",
                 "PageType": "产品聚合页", 
                 "URL": best_url
             })
        
        # 2. 分类页 (Category)
        if pools["产品分类页"]:
             # 选一个代表
             best_url = sorted(pools["产品分类页"], key=lambda x: (len(x), x))[0]
             slug = get_slug_identifier(best_url)
             final_rows.append({
                 "Project": project_name, 
                 "Category": "产品",
                 "PageType": f"产品分类页-{slug}", 
                 "URL": best_url
             })
        elif not pools["产品聚合页"] and pools["产品详情页"]: 
             # 如果没有聚合页和分类页，但有详情页，可能详情页的上级就是列表，这里暂不处理复杂反推
             pass

        # 3. 详情页
        if pools["产品详情页"]:
            sorted_prods = sorted(pools["产品详情页"], key=lambda x: (len(x), x))
            # 选一个中等长度的，避免选中极其复杂的参数页
            idx = len(sorted_prods) // 2
            best_detail = sorted_prods[idx]
            
            slug = get_slug_identifier(best_detail)
            final_rows.append({
                "Project": project_name, 
                "Category": "产品",
                "PageType": f"产品单页-{slug}", 
                "URL": best_detail
            })

    # 6. 输出结果
    result_df = pd.DataFrame(final_rows)
    
    # 调整列顺序
    if not result_df.empty:
        # 新增 Category 列，PageType 作为唯一文件名标识
        result_df = result_df[['Project', 'Category', 'PageType', 'URL']]
        result_df.to_excel(OUTPUT_FILE, index=False)
        print(f"\n✨ 成功处理！已生成文件: {OUTPUT_FILE}")
        print(f"📊 总计生成 {len(result_df)} 条监控规则")
        os.startfile(OUTPUT_FILE)
    else:
        print("⚠️ 未匹配到任何有效页面，请检查输入文件数据。")

if __name__ == "__main__":
    main()