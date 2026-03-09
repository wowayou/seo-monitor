# 🕵️ SEO 自动化监控与巡检工具集 (SEO Monitor & Inspection Suite)

本项目包含一套完整的自动化工具，用于批量获取网站关键页面、执行自动化截图巡检以及生成可视化报告。旨在帮助 SEO 人员减少重复性劳动，实现对多站点（如 50+ 项目）的高效监控。

---

## 📂 核心脚本概览

整个工作流分为 **"URL列表生成"** 和 **"自动化巡检"** 两个阶段。

| 阶段 | 脚本文件 | 功能描述 | 适用场景 |
| :--- | :--- | :--- | :--- |
| **1. 获取列表** | `generate_monitor_list_v5_crawler.py` | **(推荐)** 智能爬虫版。无需第三方数据，直接输入首页链接，自动模拟真人浏览、处理弹窗、抓取并分类关键页面。 | 只有域名列表，需要快速生成监控规则时。支持电子烟网站年龄验证。 |
| **1. 获取列表** | `generate_monitor_list_v4.py` | **(离线版)** 基于 Screaming Frog 导出数据。通过算法从庞大的爬虫数据中清洗、分类并提取代表性页面。 | 已有 Screaming Frog 的详细爬取数据 (Excel/CSV)，需要精准清洗时。 |
| **2. 执行巡检** | `screen-bot-latest.py` | **(核心)** 读取生成的 URL 列表，批量截图、检查状态码，并生成可交互的 HTML 对比报告。 | 日常巡检、UI 回归测试、页面状态监控。 |

---

## 🛠️ 环境准备

确保已安装 Python 3.8+，并安装以下依赖库：

```bash
pip install pandas playwright openpyxl xlsxwriter requests tqdm
playwright install chromium  # 安装浏览器内核
```

---

## 🚀 使用指南

### 第一步：生成监控列表 (Generate URL List)

你需要先生成一份标准的 `urls.xlsx` 文件，供巡检机器人使用。

#### 🅰️ 方案 A：使用智能爬虫 (v5 Crawler) - *推荐*

无需任何前置数据，直接让脚本去跑。

1.  准备一个 TXT 文件（每行一个 URL）或 Excel 文件（含 URL 列）。
2.  运行脚本：
    ```bash
    python generate_monitor_list_v5_crawler.py
    ```
3.  **核心优势**：
    *   **自动分类**：自动识别首页、产品、新闻、FAQ、联系我们等页面。
    *   **智能补全**：如果首页找不到产品详情，会自动进入分类页深挖。
    *   **弹窗突破**：内置逻辑自动点击 "21+" 或 "Enter Site" 等年龄验证弹窗（针对电子烟/成人用品网站）。
    *   **SEO 过滤**：可选开启 "Check Indexable"，自动剔除 Noindex 和 404 页面。

#### 🅱️ 方案 B：使用 Screaming Frog 数据 (v4 Processor)

如果你习惯用尖叫青蛙 (Screaming Frog) 爬取数据，可以使用此脚本进行清洗。

1.  将 Screaming Frog 的导出结果保存为 Excel 或 CSV。
2.  运行脚本：
    ```bash
    python generate_monitor_list_v4.py
    ```

<details>
<summary>📘 <b>附录：Screaming Frog 最佳配置指南 (点击展开)</b></summary>

为了获取最佳数据源，建议按以下步骤配置 Screaming Frog：

1.  **设置为列表模式 (List Mode)**：
    *   点击顶部菜单 `Mode` > 选择 `List`。
    *   *说明：List 模式专为批量处理多个不同域名设计。*

2.  **配置爬取深度 (关键)**：
    *   点击 `Configuration` > `Spider` > `Limits`。
    *   勾选 `Limit Crawl Depth`，数值设为 **1** 或 **2**。
    *   *说明：设为 1 仅爬取首页链接；设为 2 会进入更深一层（数据量较大）。*
    *   **(重要)** 在 `Crawl` 选项卡中，确保勾选 `Follow Internal Nofollow`。

3.  **筛选与导出**：
    *   爬取完成后，all那里 选择 html。
    *   导出筛选后的 Excel 用于脚本输入。

</details>

---

### 第二步：执行自动化巡检 (Run Inspector)

有了 `urls.xlsx` 后，就可以启动巡检机器人了。

1.  运行脚本：
    ```bash
    python screen-bot-latest.py
    ```
2.  **操作流程**：
    *   在弹出的配置窗口中，选择 `urls.xlsx` 文件。
    *   设置 **输出目录** (Output Path)。
    *   点击 **开始检查**。

---

## 💡 监控策略：为什么需要检查这些页面？

我们的监控策略覆盖了网站的核心生命周期：

1.  **首页 (Home)**: 门面担当，检查是否 200 OK，关键 Banner 是否加载。
2.  **产品详情页 (Product Detail) ⭐ 极重要**:
    *   *理由*：聚合页通常只读取简单的标题和图，而详情页涉及**复杂数据库查询、多图轮播、价格加载**等逻辑，最容易报错。
    *   *策略*：每个项目挑选 1 个具有代表性的产品页进行深度监控。
3.  **新闻/文章页 (Blog Post)**: 检查内容模板是否正常，发布日期是否显示。
4.  **Sitemap / Robots.txt**: SEO 的命脉，防止误操作导致全站被封禁（如误写 `Disallow: /`）。

---

## 🔍 常见问题与排查 (Troubleshooting)

### 1. 报告解读：三种超时级别

| 错误信息示例 | 诊断结论 | 严重程度 |
| :--- | :--- | :--- |
| `Timeout 30000ms exceeded` (goto) | **服务器/网络极差**。网站连骨架都加载不出来。 | 🔥🔥🔥 (P0级事故) |
| `Timeout 45000ms exceeded` (scroll) | **页面过长或懒加载失效**。用户体验差，滑不动。 | 🔥🔥 (体验问题) |
| `Timeout 20000ms exceeded` (screenshot) | **本地电脑卡顿**。建议减少并发数 (`CONCURRENT_TASKS`)。 | 🔥 (环境问题) |

### 2. 如何判断是 "网站挂了" 还是 "我网卡了"？

建议在 URL 列表第一行加一个基准网站（如百度/谷歌）。
*   **单点故障**：如果百度秒开，只有项目 A 超时 -> **项目 A 的问题**。
*   **集体阵亡**：如果百度也超时，或者所有项目都变慢 -> **你的网络问题**（VPN不稳定或带宽占满）。

### 3. 高级配置建议

*   **并发控制**：默认并发为 2。如果你的网络较差（如访问海外服务器），建议将 `CONCURRENT_TASKS` 设为 **1**。
*   **代理设置**：脚本默认不走系统代理。如需加速海外访问，请在代码中配置 `PROXY_SERVER` (如 `http://127.0.0.1:7890`)。
*   **反爬虫**：脚本已内置 `User-Agent` 伪装和==常见追踪代码（GA, Facebook Pixel）屏蔽==，以提升速度并降低被拦截概率。

---

## 📊 产出物 (Outputs)

脚本执行完毕后，会在输出目录生成如下结构的报告：

```text
SEO_Reports/
└── 2026-01-15/                  # 按日期归档
    ├── visual_report.html       # 🏆 可视化交互报告 (推荐)
    ├── summary_report.html      # 简易版报告
    ├── inspection_results.csv   # 原始数据
    └── [Project_Name]/          # 各项目文件夹
        ├── 首页.png
        ├── 产品聚合页.png
        └── ...
```

### 🌟 Visual Report 交互功能
*   **键盘导航**：支持 `←` `→` 键快速切换截图。
*   **状态保持**：刷新浏览器或点击返回，能记住当前浏览的位置（基于 URL Hash）。
*   **原图查看**：点击图片可查看高清大图，点击下载按钮可保存证据。

---

## 🗓️ 开发路线图 (Roadmap)

*   [x] **v4**: 支持 Screaming Frog 数据清洗与智能分类。
*   [x] **v5**: 实现基于 Playwright 的无头浏览器爬虫，支持动态内容与弹窗处理。
*   [x] **Inspector**: 支持 GUI、断点续传、实时存档、暂停/恢复。
*   [ ] **Next**: 集成 SSIM 图像识别算法，自动对比今日截图与基准图，实现像素级异常报警。

可以实时写入 实时查看吗？（属于强化，暂时不需要）

优化截图保存格式？

![image-20260115113920989](readme.assets/image-20260115113920989.png)



---

- [ ] urls.xlsx 丰富

产品详情页和新闻详情页的补充；

对应关系的微调

---

bug?

截取的图片，页眉怎么在下边？

`file:///C:/Users/xhl/Desktop/SEO_Reports/2026-01-15/TRODAT/%E6%96%B0%E9%97%BB%E8%81%9A%E5%90%88%E9%A1%B5.png`

应该是因为设置了 sticky-header 不怎么影响；

```html
<div id="sticky-header" class="menu-area sticky-menu" style="-webkit-box-shadow: 0 10px 15px rgb(25 25 25 / .1);
    box-shadow: 0 10px 15px rgb(25 25 25 / .1);">
                <div class="container custom-container">
                    <div class="row">
                        <div class="col-12">
                            <div class="mobile-nav-toggler"><i class="flaticon-layout"></i></div>
                            <div class="menu-wrap">
                                <nav class="menu-nav">
                                    <div class="logo">
                                        <a href="/"><img src="https://www.trodatcn.com/wp-content/uploads/2025/09/logo.png" alt="Logo"></a>
                                    </div>
                                    <div class="navbar-wrap main-menu d-none d-xl-flex">
                                        <ul class="navigation">
                                            <li class=" menu-item-has-children"><a href="https://www.trodatcn.com/" class="section-link">Home</a>
                                                <!--<ul class="sub-menu">-->
                                                <!--    <li class="active"><a href="index.html">Home One</a></li>-->
                                                <!--    <li><a href="index-2.html">Home Two</a></li>-->
                                                <!--    <li><a href="index-3.html">Home Three</a></li>-->
                                                <!--</ul>-->
                                            <div class="dropdown-btn"><span class="fas fa-angle-down"></span></div></li>
                                            <!--<li><a href="#features" class="section-link">Features</a></li>-->
                                            <!--<li><a href="#paroller" class="section-link">Product</a></li>-->
                                            <!--<li><a href="#ingredient" class="section-link">Ingredient</a></li>-->
                                            <!--<li><a href="#pricing" class="section-link">Pricing</a></li>-->
                                            <li class=" menu-item-has-children"><a href="https://www.trodatcn.com/products/">Products</a>
                                                <ul class="sub-menu">
                                                                                                                <li><a href="https://www.trodatcn.com/dredging-device/" class="lists">Dredging Device</a></li>
                                                                                                                <li><a href="https://www.trodatcn.com/enginegenerator-set/" class="lists">Engine&amp;Generator set</a></li>
                                                                                                                <li><a href="https://www.trodatcn.com/dredging-pump/" class="lists">Dredging Pump</a></li>
                                                                                                                <li><a href="https://www.trodatcn.com/deck-machinery/" class="lists">Deck machinery</a></li>
                                                                                                                <li><a href="https://www.trodatcn.com/suction-and-discharge-pipeline-system/" class="lists">Suction and discharge pipeline system</a></li>
                                                                                                                <li><a href="https://www.trodatcn.com/dredging-instruments/" class="lists">Dredging instruments</a></li>
                                                                                                                <li><a href="https://www.trodatcn.com/outfitting/" class="lists">Outfitting</a></li>
                                                                                                                <li><a href="https://www.trodatcn.com/special-equipment-for-dredging-maintenance/" class="lists">Special equipment for dredging maintenance</a></li>
                                                          
                                                </ul>
                                            <div class="dropdown-btn"><span class="fas fa-angle-down"></span></div></li>
                                            <li class="active menu-item-has-children"><a href="https://www.trodatcn.com/news/" class="section-link">News</a>
                                                <ul class="sub-menu">
                                                                                                                <li><a href="https://www.trodatcn.com/news_category/company-news/" class="lists">Company News</a></li>
                                                                                                                <li><a href="https://www.trodatcn.com/news_category/industry-news/" class="lists">Industry News</a></li>
                                                                                                    </ul>
                                            <div class="dropdown-btn"><span class="fas fa-angle-down"></span></div></li>
                                            <li class=" menu-item-has-children"><a href="https://www.trodatcn.com/application/">Application</a><div class="dropdown-btn"><span class="fas fa-angle-down"></span></div></li>
                                            <li class=" menu-item-has-children"><a href="https://www.trodatcn.com/service/">Service</a><div class="dropdown-btn"><span class="fas fa-angle-down"></span></div></li>
                                            <li class=" menu-item-has-children"><a href="https://www.trodatcn.com/about/">About Us</a><div class="dropdown-btn"><span class="fas fa-angle-down"></span></div></li>
                                            <li class=" menu-item-has-children"><a href="https://www.trodatcn.com/contact/">Contact Us</a><div class="dropdown-btn"><span class="fas fa-angle-down"></span></div></li>
                                        </ul>
                                    </div>
                                    <div class="header-action d-none d-sm-block">
                                        <ul>
                                            <li class="header-search"><a href="#"><i class="flaticon-search"></i></a></li>
                                            <li class="offCanvas-btn d-none d-xl-block"><a href="#" class="navSidebar-button"><i class="flaticon-layout"></i></a>
                                            </li>
                                        </ul>
                                    </div>
                                </nav>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
```

## 局限性

![image-20260203135512159](readme.assets/image-20260203135512159.png)

这种能访问到（cloudfalre fake verification 问题）；也能截图。

但是我们通过浏览器访问就是不行的！=> 所以还需要调整巡检脚本。

使用 playwright 来模拟浏览器？？？

解决方案

```java
针对“延迟触发的假验证攻击”，研究在无头浏览器（Playwright/Puppeteer）中实现“真实用户模拟器”的技术方案，包括模拟随机停留时间、鼠标移动、页面滚动，并识别注入式验证组件。
```

模拟随机停留时间，鼠标移动

---

为啥脚本就能访问这种呢？

**脚本差异点**：自动化脚本（Playwright）与真实用户的行为模式（浏览器指纹、交互逻辑）完全不同，导致恶意脚本未能触发。

![image-20260203145625399](readme.assets/image-20260203145625399.png)

**缺乏“真实”交互触发**： 伪造的 Cloudflare 验证往往需要检测到 `mousemove`（鼠标移动）或 `scroll`（滚动）等**人类特有行为**后才会弹出。你的脚本虽然有滚动逻辑，但速度极快且路径机械，可能未达到恶意代码的触发阈值。

这种也返回成功（因为截图成功了！）

![image-20260209121159723](readme.assets/image-20260209121159723.png)

==总结：还是**需要打开截图**看一下！！！==

---

**中间退出功能是没有实现的；**

容错机制有问题！

这种进入网页之后会跳转到短链接的问题也不能检查出来！！！

而且截图也是正常的！（是会影响用户的体验的）

![image-20260209123714897](readme.assets/image-20260209123714897.png)

301 重定向的问题；

---

果然还是**得人工**！（整理一份人工检查的url吧）

---

无法完全模拟呀！

