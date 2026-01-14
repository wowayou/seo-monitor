import asyncio
import os
import time
import signal
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime
import pandas as pd
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# ================= ⚙️ 全局配置与常量 =================

# 强力屏蔽列表 (提速 + 防污染)
BLOCK_DOMAINS = [
    "google-analytics.com", "googletagmanager.com", "googleadservices.com", "doubleclick.net",
    "facebook.net", "connect.facebook.net", "tiktok.com", "pixel.wp.com",
    "hm.baidu.com", "cnzz.com", "hotjar.com", "sentry.io", "clarity.ms"
]

STOP_REQUESTED = False

class InspectionConfig:
    def __init__(self):
        self.excel_path = ""
        self.output_root = ""
        self.proxy_server = ""
        self.concurrent_tasks = 2
        self.page_timeout = 60000  # ms
        self.max_retries = 2
        self.strict_load_mode = True
        self.resume = True # 是否断点续传(如果想要重新巡检的化，需要将该值设为False)

# ================= 📊 报告生成模块 =================
class ReportGenerator:
    @staticmethod
    def create_project_summary(results, save_dir):
        """创建项目汇总报告"""
        project_stats = {}
        for res in results:
            project = res['Project']
            if project not in project_stats:
                project_stats[project] = {'total': 0, 'success': 0, 'failed': 0}
            project_stats[project]['total'] += 1
            if res['Status'] == 'Success':
                project_stats[project]['success'] += 1
            else:
                project_stats[project]['failed'] += 1
        
        html_content = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="utf-8">
            <title>项目总览 - 巡检报告 {datetime.now().strftime('%Y-%m-%d')}</title>
            <style>
                :root {{ --primary: #2c3e50; --success: #27ae60; --danger: #e74c3c; --warning: #f39c12; --bg: #f4f6f9; }}
                body {{ font-family: 'Segoe UI', sans-serif; background: var(--bg); padding: 20px; color: #333; }}
                .header {{ text-align: center; padding: 20px; background: white; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
                .stats-container {{ display: flex; flex-wrap: wrap; gap: 15px; justify-content: center; margin-bottom: 20px; }}
                .stat-card {{ padding: 15px 25px; border-radius: 8px; color: white; text-align: center; min-width: 150px; font-weight: bold; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                .total {{ background: linear-gradient(135deg, #7f8c8d, #95a5a6); }}
                .success {{ background: linear-gradient(135deg, #2ecc71, #27ae60); }}
                .failed {{ background: linear-gradient(135deg, #e74c3c, #c0392b); }}
                .projects-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 20px; }}
                .project-card {{ background: white; border-radius: 10px; padding: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); transition: transform 0.2s; }}
                .project-card:hover {{ transform: translateY(-5px); box-shadow: 0 5px 15px rgba(0,0,0,0.1); }}
                .project-title {{ font-size: 1.3rem; font-weight: bold; margin-bottom: 15px; color: var(--primary); border-bottom: 2px solid #eee; padding-bottom: 10px; }}
                .progress-bar {{ width: 100%; height: 24px; background: #ecf0f1; border-radius: 12px; overflow: hidden; margin: 15px 0; display: flex; }}
                .progress {{ height: 100%; display: flex; align-items: center; justify-content: center; color: white; font-size: 0.8rem; font-weight: bold; transition: width 0.5s ease; }}
                .success-progress {{ background: var(--success); }}
                .failed-progress {{ background: var(--danger); }}
                .links {{ margin-top: 20px; text-align: right; }}
                .btn {{ display: inline-block; padding: 8px 16px; background: var(--primary); color: white; text-decoration: none; border-radius: 20px; margin-left: 10px; font-size: 0.9rem; transition: background 0.2s; }}
                .btn:hover {{ background: #34495e; }}
                .stat-row {{ display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 0.95rem; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>📊 项目总览 - 网站巡检日报</h2>
                <div class="stats-container">
                    <div class="stat-card total">总计任务<br>{len(results)}</div>
                    <div class="stat-card success">成功完成<br>{len([r for r in results if r['Status']=='Success'])}</div>
                    <div class="stat-card failed">失败异常<br>{len([r for r in results if r['Status']=='Failed'])}</div>
                </div>
            </div>
            
            <div class="projects-grid">
        """
        
        for project, stats in project_stats.items():
            success_pct = (stats['success'] / stats['total']) * 100 if stats['total'] > 0 else 0
            failed_pct = (stats['failed'] / stats['total']) * 100 if stats['total'] > 0 else 0
            
            html_content += f"""
            <div class="project-card">
                <div class="project-title">{project}</div>
                <div class="stat-row"><span>总计:</span> <strong>{stats['total']}</strong></div>
                <div class="stat-row"><span>成功:</span> <strong style="color:var(--success)">{stats['success']}</strong></div>
                <div class="stat-row"><span>失败:</span> <strong style="color:var(--danger)">{stats['failed']}</strong></div>
                
                <div class="progress-bar">
                    <div class="progress success-progress" style="width: {success_pct}%;">{int(success_pct)}%</div>
                    <div class="progress failed-progress" style="width: {failed_pct}%;">{int(failed_pct)}%</div>
                </div>
                <div class="links">
                    <a href="visual_report.html#{project}" class="btn">查看详情</a>
                </div>
            </div>
            """
        
        html_content += """
            </div>
        </body>
        </html>
        """
        
        summary_path = os.path.join(save_dir, "summary_report.html")
        with open(summary_path, "w", encoding="utf-8") as f: f.write(html_content)
        return summary_path

    @staticmethod
    def create_html_report(results, save_dir):
        """创建详细的可视化报告"""
        total = len(results)
        success = len([r for r in results if r['Status']=='Success'])
        failed = len([r for r in results if r['Status']=='Failed'])
        
        # 相对路径处理
        for res in results:
            if res['ScreenshotPath'] and os.path.exists(res['ScreenshotPath']):
                try:
                    res['RelPath'] = os.path.relpath(res['ScreenshotPath'], save_dir).replace('\\', '/')
                except ValueError:
                    res['RelPath'] = ""
            else:
                res['RelPath'] = ""

        html_content = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="utf-8">
            <title>巡检报告 {datetime.now().strftime('%Y-%m-%d')}</title>
            <style>
                :root {{ --primary: #2c3e50; --success: #27ae60; --danger: #e74c3c; --bg: #f4f6f9; }}
                body {{ font-family: 'Segoe UI', sans-serif; background: var(--bg); padding: 20px; color: #333; }}
                .header {{ text-align: center; padding: 20px; background: white; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
                .stats span {{ margin: 0 10px; padding: 6px 15px; border-radius: 20px; color: white; font-size: 0.95rem; font-weight: bold; }}
                .controls {{ text-align: center; margin: 20px 0; }}
                .filter-btn {{ margin: 0 5px; padding: 8px 20px; background: white; color: #555; border: 1px solid #ddd; border-radius: 20px; cursor: pointer; transition: all 0.2s; }}
                .filter-btn:hover, .filter-btn.active {{ background: var(--primary); color: white; border-color: var(--primary); }}
                .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }}
                .card {{ background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 5px rgba(0,0,0,0.05); transition: transform 0.2s; border: 1px solid #eee; }}
                .card:hover {{ transform: translateY(-3px); box-shadow: 0 5px 15px rgba(0,0,0,0.1); }}
                .project-header {{ background: #f8f9fa; padding: 10px 15px; font-weight: bold; border-left: 5px solid var(--primary); margin: 20px 0 10px 0; border-radius: 4px; display: flex; justify-content: space-between; align-items: center; }}
                .img-box {{ height: 200px; background: #eee; overflow: hidden; cursor: zoom-in; position: relative; }}
                .img-box img {{ width: 100%; height: 100%; object-fit: cover; object-position: top; transition: transform 0.3s; }}
                .img-box:hover img {{ transform: scale(1.05); }}
                .overlay-btn {{ position: absolute; bottom: 10px; right: 10px; background: rgba(0,0,0,0.7); color: white; border: none; border-radius: 4px; padding: 6px 12px; font-size: 0.8rem; cursor: pointer; backdrop-filter: blur(2px); }}
                .overlay-btn:hover {{ background: rgba(0,0,0,0.9); }}
                .info {{ padding: 12px; }}
                .info-title {{ font-weight: bold; margin-bottom: 5px; display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
                .info-meta {{ font-size: 0.85rem; color: #7f8c8d; display: flex; justify-content: space-between; align-items: center; margin-top: 8px; }}
                
                /* Modal Styles */
                .modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.92); z-index: 999; backdrop-filter: blur(5px); }}
                .modal-content {{ margin: auto; display: block; max-width: 95%; max-height: 85vh; margin-top: 60px; box-shadow: 0 0 20px rgba(0,0,0,0.5); }}
                .modal-controls {{ position: fixed; top: 0; left: 0; width: 100%; height: 50px; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }}
                .modal-btn {{ background: transparent; color: white; border: 1px solid rgba(255,255,255,0.3); padding: 5px 15px; margin: 0 5px; border-radius: 4px; cursor: pointer; font-size: 0.9rem; transition: background 0.2s; }}
                .modal-btn:hover {{ background: rgba(255,255,255,0.2); }}
                .close {{ position: absolute; top: 10px; right: 20px; color: #fff; font-size: 30px; cursor: pointer; z-index: 1001; }}
                .nav-btn {{ position: fixed; top: 50%; transform: translateY(-50%); background: rgba(255,255,255,0.1); color: white; border: none; width: 60px; height: 100px; font-size: 2rem; cursor: pointer; transition: background 0.3s; }}
                .nav-btn:hover {{ background: rgba(255,255,255,0.3); }}
                .prev {{ left: 0; border-radius: 0 10px 10px 0; }}
                .next {{ right: 0; border-radius: 10px 0 0 10px; }}
                
                #caption {{ position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); color: white; background: rgba(0,0,0,0.7); padding: 10px 20px; border-radius: 30px; font-size: 0.9rem; pointer-events: none; }}
                #caption a {{ pointer-events: auto; color: #4da6ff; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>🚀 网站巡检日报</h2>
                <div class="stats">
                    <span style="background:#7f8c8d">总数: {total}</span>
                    <span style="background:var(--success)">成功: {success}</span>
                    <span style="background:var(--danger)">失败: {failed}</span>
                </div>
            </div>
            
            <div class="controls">
                <button class="filter-btn active" onclick="filterResults('all')">全部显示</button>
                <button class="filter-btn" onclick="filterResults('success')">只看成功</button>
                <button class="filter-btn" onclick="filterResults('failed')">只看失败</button>
                <a href="summary_report.html" class="filter-btn" style="text-decoration:none; background:#9b59b6; color:white; border-color:#9b59b6;">返回总览</a>
            </div>
            
            <div id="resultsGrid">
        """

        projects = {}
        for res in results:
            project = res['Project']
            if project not in projects:
                projects[project] = []
            projects[project].append(res)
        
        for project, project_results in projects.items():
            project_success = len([r for r in project_results if r['Status'] == 'Success'])
            project_failed = len([r for r in project_results if r['Status'] == 'Failed'])
            
            html_content += f"""
            <div class="project-group" id="{project}">
                <div class="project-header">
                    <span>📂 {project}</span>
                    <span style="font-size:0.9rem; font-weight:normal">
                        <span style="color:var(--success)">✔ {project_success}</span> / 
                        <span style="color:var(--danger)">✘ {project_failed}</span>
                    </span>
                </div>
                <div class="grid">
            """
            
            for res in project_results:
                color = "#27ae60" if res['Status']=='Success' else "#e74c3c"
                status_icon = "✅" if res['Status']=='Success' else "❌"
                img_tag = f'<img src="{res["RelPath"]}" loading="lazy">' if res['RelPath'] else '<div style="padding:60px 0;text-align:center;color:#999">❌ 无预览图</div>'
                
                html_content += f"""
                <div class="card result-item" data-status="{res['Status'].lower()}">
                    <div style="height:4px; background:{color}"></div>
                    <div class="img-box" onclick="openModal('{res["RelPath"]}', '{res["URL"]}', '{res["Project"]} - {res["PageType"]}')">
                        {img_tag}
                        <button class="overlay-btn" onclick="event.stopPropagation(); window.open('{res["URL"]}', '_blank');">🔗 访问</button>
                    </div>
                    <div class="info">
                        <span class="info-title" title="{res['PageType']}">{res['PageType']}</span>
                        <div class="info-meta">
                            <span>⏱️ {res.get('LoadTime_s',0)}s</span>
                            <span style="color:{color}; font-weight:bold;">{status_icon} {res['Status']}</span>
                        </div>
                    </div>
                </div>
                """
            
            html_content += "</div></div>"

        # 插入JavaScript (保持原有逻辑但增强交互)
        html_content += """
            </div>
            
            <!-- 模态框结构 -->
            <div id="myModal" class="modal" onclick="if(event.target === this) closeModal()">
                <div class="modal-controls">
                    <span id="imageCounter" style="color:white; font-weight:bold; margin-right:20px;">0/0</span>
                    <button class="modal-btn" onclick="openCurrentUrl()">🔗 浏览器打开</button>
                    <button class="modal-btn" onclick="downloadImage()">⬇️ 下载</button>
                    <button class="modal-btn" onclick="zoomIn()">🔍 放大</button>
                    <button class="modal-btn" onclick="zoomOut()">🔍 缩小</button>
                    <button class="modal-btn" onclick="resetZoom()">⭕ 复位</button>
                    <span class="close" onclick="closeModal()">&times;</span>
                </div>
                
                <button class="nav-btn prev" onclick="changeImage(-1)">❮</button>
                <img class="modal-content" id="img01">
                <button class="nav-btn next" onclick="changeImage(1)">❯</button>
                
                <div id="caption"></div>
            </div>
            
            <script>
                let modalImages = [], modalUrls = [], modalCaptions = [];
                let currentIndex = 0;
                let scale = 1, offsetX = 0, offsetY = 0;
                let isDragging = false, startX, startY;
                
                // Initialize on load to restore state from URL hash
                window.onload = function() {
                    collectModalData();
                    const hash = window.location.hash;
                    if (hash && hash.startsWith('#view=')) {
                        const index = parseInt(hash.substring(6));
                        if (!isNaN(index) && index >= 0 && index < modalImages.length) {
                            showImage(index);
                            document.getElementById('myModal').style.display = 'block';
                        }
                    }
                };

                // Listen for hash changes (e.g. forward/back buttons)
                window.onhashchange = function() {
                    const hash = window.location.hash;
                    if (!hash || !hash.startsWith('#view=')) {
                        closeModal(false); 
                    } else {
                        const index = parseInt(hash.substring(6));
                        if (!isNaN(index) && document.getElementById('myModal').style.display !== 'block') {
                            showImage(index);
                            document.getElementById('myModal').style.display = 'block';
                        }
                    }
                };
                
                function normalize(url) {
                    try { return decodeURIComponent(url).replace(/\\\\/g, '/'); } catch(e) { return url; }
                }

                function openModal(imageSrc, url, caption) {
                    collectModalData();
                    const normSrc = normalize(imageSrc);
                    currentIndex = modalImages.findIndex(img => normalize(img).includes(normSrc));
                    
                    if(currentIndex === -1 && imageSrc) { // Fallback
                         document.getElementById('img01').src = imageSrc;
                         document.getElementById('myModal').style.display = 'block';
                         return;
                    }
                    showImage(currentIndex);
                    document.getElementById('myModal').style.display = 'block';
                    history.pushState(null, null, '#view=' + currentIndex);
                }
                
                function showImage(index) {
                    if(index < 0) index = modalImages.length - 1;
                    if(index >= modalImages.length) index = 0;
                    currentIndex = index;
                    
                    const img = document.getElementById('img01');
                    img.src = modalImages[currentIndex];
                    document.getElementById('caption').innerHTML = modalCaptions[currentIndex];
                    document.getElementById('imageCounter').innerText = (currentIndex + 1) + " / " + modalImages.length;
                    resetZoom();
                    
                    if(document.getElementById('myModal').style.display === 'block') {
                         history.replaceState(null, null, '#view=' + currentIndex);
                    }
                }
                
                function changeImage(dir) { showImage(currentIndex + dir); }
                
                function closeModal(updateHistory = true) { 
                    document.getElementById('myModal').style.display = 'none'; 
                    if(updateHistory) {
                        history.pushState(null, null, window.location.pathname + window.location.search);
                    }
                }
                
                function collectModalData() {
                    modalImages = []; modalUrls = []; modalCaptions = [];
                    document.querySelectorAll('.result-item').forEach(item => {
                        if(item.style.display !== 'none') { 
                            const img = item.querySelector('img');
                            if(img) {
                                modalImages.push(img.src);
                                const onclickAttr = item.querySelector('.img-box').getAttribute('onclick');
                                const parts = onclickAttr.split("'");
                                modalUrls.push(parts[3]);
                                modalCaptions.push(parts[5]);
                            }
                        }
                    });
                }
                
                function filterResults(status) {
                    document.querySelectorAll('.result-item').forEach(item => {
                        if(status === 'all' || item.dataset.status === status) item.style.display = 'block';
                        else item.style.display = 'none';
                    });
                    document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
                    event.target.classList.add('active');
                    collectModalData(); // Re-collect after filtering
                }

                // Zoom & Drag Logic
                function zoomIn() { scale += 0.2; applyZoom(); }
                function zoomOut() { if(scale > 0.4) scale -= 0.2; applyZoom(); }
                function resetZoom() { scale = 1; offsetX = 0; offsetY = 0; applyZoom(); }
                function applyZoom() { document.getElementById('img01').style.transform = `scale(${scale}) translate(${offsetX}px, ${offsetY}px)`; }
                
                function openCurrentUrl() { window.open(modalUrls[currentIndex], '_blank'); }
                function downloadImage() { 
                    const a = document.createElement('a');
                    a.href = modalImages[currentIndex];
                    a.download = '';
                    a.target = '_blank';
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                }

                // Keyboard support
                document.addEventListener('keydown', e => {
                    if(document.getElementById('myModal').style.display === 'block') {
                        if(e.key === 'ArrowLeft') changeImage(-1);
                        if(e.key === 'ArrowRight') changeImage(1);
                        if(e.key === 'Escape') closeModal();
                    }
                });
            </script>
        </body>
        </html>
        """
        
        report_path = os.path.join(save_dir, "visual_report.html")
        with open(report_path, "w", encoding="utf-8") as f: f.write(html_content)
        return report_path

# ================= 🕸️ 核心采集逻辑 =================
class WebsiteInspector:
    def __init__(self, config: InspectionConfig, log_callback=None):
        self.cfg = config
        self.log_callback = log_callback or print
        self.paused = False # 暂停控制标志
        self.autosave_file = None # 自动保存文件路径

    def init_autosave(self):
        """初始化自动保存文件"""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            save_dir = os.path.join(self.cfg.output_root, today)
            os.makedirs(save_dir, exist_ok=True)
            self.autosave_file = os.path.join(save_dir, "_autosave_progress.csv")
            
            # 如果文件不存在，写入表头
            if not os.path.exists(self.autosave_file):
                pd.DataFrame(columns=["Project", "PageType", "URL", "Status", "LoadTime_s", "ScreenshotPath", "ErrorMessage"]).to_csv(self.autosave_file, index=False, encoding='utf-8-sig')
        except Exception as e:
            self.log(f"⚠️ 无法初始化自动保存: {e}")

    def append_to_autosave(self, result):
        """追加单条结果到CSV"""
        if not self.autosave_file: return
        try:
            pd.DataFrame([result]).to_csv(self.autosave_file, mode='a', header=False, index=False, encoding='utf-8-sig')
        except: pass

    def log(self, message):
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)

    async def enhanced_scroll_and_wait(self, page):
        """深度优化的滚动策略"""
        try:
            last_height = await page.evaluate("document.body.scrollHeight")
            
            # 动态调整滚动次数，页面越长滚动越多，上限30次
            max_scrolls = 30
            
            for i in range(max_scrolls):
                if STOP_REQUESTED: break
                while self.paused: await asyncio.sleep(0.5)
                
                # 1. 滚动到底部
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                
                # 2. 智能等待：检查网络空闲，但有超时限制
                try:
                    # 等待网络空闲（无网络请求持续500ms），最长等1.5秒
                    await page.wait_for_load_state("networkidle", timeout=1500)
                except:
                    await asyncio.sleep(1) # 如果网络一直忙，就硬等待1秒
                
                # 3. 检查高度变化
                new_height = await page.evaluate("document.body.scrollHeight")
                
                if new_height == last_height:
                    # 高度未变，尝试“回拉”操作触发某些懒加载
                    await page.evaluate("window.scrollBy(0, -500)")
                    await asyncio.sleep(0.5)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    
                    # 再次检查
                    final_height = await page.evaluate("document.body.scrollHeight")
                    if final_height == last_height:
                        # 确实到底了
                        break
                    last_height = final_height
                else:
                    last_height = new_height
            
            # 滚回顶部再分段滚下（防止中间内容漏加载）
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(0.5)
            
            # 快速分段扫描
            viewport_height = 1080
            current_y = 0
            while current_y < last_height:
                if STOP_REQUESTED: break
                current_y += viewport_height
                await page.evaluate(f"window.scrollTo(0, {current_y})")
                await asyncio.sleep(0.2)
            
            # 最后定格在底部或顶部（根据需求，这里定格在顶部以便看首屏，或者全屏截图通常不需要特定位置）
            # Playwright full_page截图会自动滚动，但手动滚动是为了触发JS懒加载
            await asyncio.sleep(1)
            
        except Exception as e:
            self.log(f"   [滚动微扰] {str(e)[:50]}")

    async def capture_task(self, browser, row, semaphore, results_list):
        if STOP_REQUESTED: return 
        async with semaphore:
            project = str(row['Project']).strip()
            page_type = str(row['PageType']).strip()
            url = str(row['URL']).strip()
            
            res = {"Project": project, "PageType": page_type, "URL": url, "Status": "Pending", "LoadTime_s": 0.0, "ScreenshotPath": ""}
            
            # 创建日期目录
            today = datetime.now().strftime("%Y-%m-%d")
            save_dir = os.path.join(self.cfg.output_root, today, project)
            os.makedirs(save_dir, exist_ok=True)
            
            # 文件名处理：去除非法字符
            safe_name = "".join([c for c in page_type if c.isalnum() or c in (' ', '-', '_')]).strip()
            save_path = os.path.join(save_dir, f"{safe_name}.png")
            
            context = None
            try:
                # 随机User-Agent (简单的两个现代UA轮换，避免太复杂)
                ua_list = [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ]
                ua = ua_list[int(time.time()) % 2]
                
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent=ua,
                    ignore_https_errors=True,
                    device_scale_factor=1
                )
                
                page = await context.new_page()

                # 屏蔽请求
                for d in BLOCK_DOMAINS:
                    try: await page.route(f"**/*{d}*", lambda r: r.abort())
                    except: pass

                # 重试循环
                for attempt in range(self.cfg.max_retries + 1):
                    if STOP_REQUESTED: break
                    while self.paused: await asyncio.sleep(0.5)
                    try:
                        start_t = time.time()
                        wait_policy = "networkidle" if self.cfg.strict_load_mode else "domcontentloaded"
                        
                        try:
                            await page.goto(url, timeout=self.cfg.page_timeout, wait_until=wait_policy)
                        except PlaywrightTimeoutError:
                            self.log(f"   [⚠️ 超时] {project} - {page_type} (切换极速模式)")
                            await page.goto(url, timeout=30000, wait_until="domcontentloaded")

                        await self.enhanced_scroll_and_wait(page)
                        
                        res["LoadTime_s"] = round(time.time() - start_t, 2)
                        await page.screenshot(path=save_path, full_page=True, type='png')
                        
                        res["Status"] = "Success"
                        res["ScreenshotPath"] = save_path
                        self.log(f"[✅ 成功] {project} - {page_type}")
                        break
                    except Exception as e:
                        err = str(e).splitlines()[0][:100]
                        if attempt == self.cfg.max_retries:
                            res["Status"] = "Failed"
                            res["ErrorMessage"] = err
                            self.log(f"[❌ 失败] {project} - {page_type}: {err}")
                            # 记录错误日志
                            with open(os.path.join(save_dir, "error_log.txt"), "a", encoding='utf-8') as f:
                                f.write(f"[{datetime.now()}] {url}\nError: {e}\n\n")
                        else:
                            self.log(f"   [重试 {attempt+1}] {project} - {page_type}")
                            await asyncio.sleep(2)
            
            except Exception as e:
                self.log(f"[💥 系统错误] {project}: {e}")
            finally:
                if context:
                    try: await context.close()
                    except: pass
            
            results_list.append(res)
            self.append_to_autosave(res) # 实时保存

    async def run(self):
        self.log(f"🚀 开始任务 | 并发数: {self.cfg.concurrent_tasks} | 代理: {self.cfg.proxy_server or '无'}")
        
        try:
            self.init_autosave() # 初始化保存
            
            # 如果不续传且文件存在，则清理旧记录（init_autosave已经初始化了路径）
            if not self.cfg.resume and self.autosave_file and os.path.exists(self.autosave_file):
                 try:
                     os.remove(self.autosave_file)
                     self.init_autosave() # 重建表头
                     self.log("🧹 已清理旧进度，重新开始...")
                 except Exception as e:
                     self.log(f"⚠️ 清理旧进度失败: {e}")

            df = pd.read_excel(self.cfg.excel_path, dtype=str).dropna(subset=['URL'])
        except Exception as e:
            self.log(f"❌ 读取Excel失败: {e}")
            return

        results = []
        
        # 断点续传逻辑
        if self.cfg.resume and self.autosave_file and os.path.exists(self.autosave_file):
            try:
                saved_df = pd.read_csv(self.autosave_file)
                if not saved_df.empty:
                    # 加载旧数据到结果列表，确保报告完整
                    results.extend(saved_df.to_dict('records'))
                    
                    # 获取已处理的URL集合
                    processed_urls = set(saved_df['URL'].astype(str).str.strip())
                    
                    # 过滤待处理任务
                    original_count = len(df)
                    df = df[~df['URL'].str.strip().isin(processed_urls)]
                    skipped_count = original_count - len(df)
                    
                    self.log(f"🔄 断点续传模式: 已加载 {len(saved_df)} 条历史记录，跳过 {skipped_count} 个已完成任务。")
            except Exception as e:
                self.log(f"⚠️ 读取历史进度失败，将重新检查: {e}")

        async with async_playwright() as p:
            browser_args = {"headless": True, "args": ['--no-sandbox', '--disable-setuid-sandbox']}
            if self.cfg.proxy_server:
                browser_args["proxy"] = {"server": self.cfg.proxy_server}
            
            try:
                browser = await p.chromium.launch(**browser_args)
            except Exception as e:
                self.log(f"❌ 浏览器启动失败: {e}")
                return

            semaphore = asyncio.Semaphore(self.cfg.concurrent_tasks)
            tasks = [self.capture_task(browser, row, semaphore, results) for _, row in df.iterrows()]
            
            try:
                await asyncio.gather(*tasks)
            except KeyboardInterrupt:
                global STOP_REQUESTED
                STOP_REQUESTED = True
                self.log("\n🛑 用户停止！正在保存已有数据...")
            finally:
                try: await browser.close()
                except: pass

        if not results:
            self.log("⚠️ 没有生成任何数据")
            return

        # 生成报告
        self.log("📊 正在生成报告...")
        today_folder = datetime.now().strftime("%Y-%m-%d")
        report_dir = os.path.join(self.cfg.output_root, today_folder)
        os.makedirs(report_dir, exist_ok=True)
        
        # 1. Excel
        try:
            pd.DataFrame(results).to_excel(os.path.join(report_dir, "report.xlsx"), index=False)
        except: pass
        
        # 2. HTML
        try:
            html_path = ReportGenerator.create_html_report(results, report_dir)
            self.log(f"✅ 详细报告: {html_path}")
        except Exception as e:
            self.log(f"❌ HTML报告生成失败: {e}")

        # 3. Summary
        try:
            summary_path = ReportGenerator.create_project_summary(results, report_dir)
            self.log(f"✅ 汇总报告: {summary_path}")
            os.startfile(summary_path) # Windows Only
        except: pass
        
        self.log("✨ 全部任务完成!")

# ================= 🖥️ GUI 界面 =================
class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SEO自动巡检工具 v2.1")
        self.root.geometry("600x600")  # 增加高度，防止内容遮挡
        self.root.resizable(True, True) # 允许调整大小
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # 样式
        style = ttk.Style()
        style.configure("TButton", padding=6, font=('Microsoft YaHei', 10))
        style.configure("TLabel", font=('Microsoft YaHei', 10))
        style.configure("TEntry", padding=4)
        
        # 变量
        self.excel_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.proxy = tk.StringVar()
        self.concurrency = tk.IntVar(value=2)
        
        # 尝试自动寻找同级目录的xlsx
        default_excel = os.path.join(os.path.dirname(os.path.abspath(__file__)), "urls.xlsx")
        if os.path.exists(default_excel):
            self.excel_path.set(default_excel)
            
        # 默认输出路径为桌面
        desktop = os.path.join(os.path.expanduser("~"), "Desktop", "SEO_Reports")
        self.output_path.set(desktop)

        self.inspector = None # Inspector 实例引用
        self._create_widgets()

    def on_closing(self):
        if self.inspector: # 如果有任务实例
            if messagebox.askokcancel("退出", "⚠️ 正在进行任务！\n\n确定要退出吗？\n程序将等待当前步骤完成并生成报告，请勿强制关闭。"):
                global STOP_REQUESTED
                STOP_REQUESTED = True
                
                # 更新界面状态
                self.start_btn.config(text="🛑 正在停止并保存...", state='disabled')
                self.pause_btn.config(state='disabled')
                self.log("\n🛑 用户请求退出，正在等待任务安全结束并保存报告...")
                
                # 启动监测循环，等待后台线程结束
                self.check_thread_done()
        else:
            self.root.destroy()
            sys.exit(0)

    def check_thread_done(self):
        # 检查是否只剩下主线程 (GUI线程)
        # 注意：如果有其他daemon线程可能需要更精确的判断，但这里主要是有个work thread
        if threading.active_count() <= 1: 
            self.root.destroy()
            sys.exit(0)
        else:
            self.root.after(500, self.check_thread_done)

    def _create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 0. 底部按钮区域
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        
        self.start_btn = ttk.Button(btn_frame, text="开始巡检", command=self.start_inspection)
        self.start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        self.pause_btn = ttk.Button(btn_frame, text="暂停", command=self.toggle_pause, state='disabled')
        self.pause_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        # 标题
        ttk.Label(main_frame, text="🚀 网站自动巡检配置", font=('Microsoft YaHei', 16, 'bold')).pack(side=tk.TOP, pady=(0, 20))
        
        # 1. Excel 选择
        frame1 = ttk.LabelFrame(main_frame, text="1. 任务文件 (Excel)", padding=10)
        frame1.pack(side=tk.TOP, fill=tk.X, pady=5)
        ttk.Entry(frame1, textvariable=self.excel_path, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(frame1, text="浏览...", command=self.browse_excel).pack(side=tk.RIGHT)
        
        # 2. 输出路径
        frame2 = ttk.LabelFrame(main_frame, text="2. 报告存储路径", padding=10)
        frame2.pack(side=tk.TOP, fill=tk.X, pady=5)
        ttk.Entry(frame2, textvariable=self.output_path, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(frame2, text="选择...", command=self.browse_output).pack(side=tk.RIGHT)
        
        # 3. 高级设置
        frame3 = ttk.LabelFrame(main_frame, text="3. 高级设置", padding=10)
        frame3.pack(side=tk.TOP, fill=tk.X, pady=5)
        
        ttk.Label(frame3, text="代理地址 (可选):").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame3, textvariable=self.proxy, width=30).grid(row=0, column=1, padx=5)
        ttk.Label(frame3, text="例如: http://127.0.0.1:7890").grid(row=0, column=2, sticky=tk.W, padx=5)
        
        ttk.Label(frame3, text="并发任务数:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(frame3, from_=1, to=10, textvariable=self.concurrency, width=5).grid(row=1, column=1, sticky=tk.W, padx=5)
        
        # 4. 日志区域 (最后pack，占据剩余中间空间)
        ttk.Label(main_frame, text="运行日志:").pack(side=tk.TOP, anchor=tk.W, pady=(10, 0))
        self.log_text = tk.Text(main_frame, height=8, width=70, font=('Consolas', 9), state='disabled')
        self.log_text.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=5)

    def browse_excel(self):
        f = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx;*.xls")])
        if f: self.excel_path.set(f)

    def browse_output(self):
        d = filedialog.askdirectory()
        if d: self.output_path.set(d)

    def log(self, msg):
        def _update():
            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, str(msg) + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state='disabled')
        self.root.after(0, _update)

    def start_inspection(self):
        # 验证
        if not os.path.exists(self.excel_path.get()):
            messagebox.showerror("错误", "请选择有效的 Excel 文件！")
            return
        if not self.output_path.get():
            messagebox.showerror("错误", "请选择报告存储路径！")
            return
            
        # 锁定按钮
        self.start_btn.config(state='disabled', text="正在运行...")
        
        # 配置对象
        cfg = InspectionConfig()
        cfg.excel_path = self.excel_path.get()
        cfg.output_root = self.output_path.get()
        cfg.proxy_server = self.proxy.get().strip() or None
        cfg.concurrent_tasks = self.concurrency.get()
        
        # 检查是否可以断点续传
        today = datetime.now().strftime("%Y-%m-%d")
        autosave_path = os.path.join(cfg.output_root, today, "_autosave_progress.csv")
        if os.path.exists(autosave_path) and os.path.getsize(autosave_path) > 100:
            # 简单判断文件存在且有内容（大于表头）
            ans = messagebox.askyesno("发现未完成进度", f"检测到今日 ({today}) 有任务记录。\n\n是否继续上次的进度？\n\n【是】：仅检查剩余的网址\n【否】：重新开始（覆盖旧记录）")
            cfg.resume = ans
        
        # 在新线程中运行Async循环，防止卡死GUI
        thread = threading.Thread(target=self.run_async_loop, args=(cfg,), daemon=True)
        thread.start()

    def toggle_pause(self):
        if not self.inspector: return
        self.inspector.paused = not self.inspector.paused
        if self.inspector.paused:
            self.pause_btn.config(text="继续运行")
            self.log("⚠️ 任务已暂停...")
        else:
            self.pause_btn.config(text="暂停")
            self.log("▶️ 任务继续...")

    def run_async_loop(self, cfg):
        self.inspector = WebsiteInspector(cfg, log_callback=self.log)
        # 启用暂停按钮
        self.root.after(0, lambda: self.pause_btn.config(state='normal', text="暂停"))
        
        asyncio.run(self.inspector.run())
        
        # 恢复按钮
        self.root.after(0, lambda: self.start_btn.config(state='normal', text="开始巡检"))
        self.root.after(0, lambda: self.pause_btn.config(state='disabled', text="暂停"))
        self.root.after(0, lambda: messagebox.showinfo("完成", "巡检任务已完成！"))

def main():
    root = tk.Tk()
    app = LauncherApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
