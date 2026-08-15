# 娱乐自动监控台 · 云端自治版

把"抓四平台热点 → 出图文 → 写 data.json → 发布"整套搬到 **GitHub Actions（免费）+ GitHub Pages（免费）**，
跑在 GitHub 云端，**不依赖你本地电脑**，关机/休眠都不影响，每小时自动刷新一次。

## 它怎么替代原来 WorkBuddy 的两步
- **抓热点**：`scraper.py` 用 Python 直接 HTTP 抓公开榜单页（微博 / 抖音 / 小红书 / B站），多源容错，单站挂了其余照常。
- **出图**：用 [Pollinations.ai](https://pollinations.ai)（免费、无需 key），只把图片 **URL** 写进 `data.json`，前端直接引，**不往 git 塞二进制**。
- **出文**：调用 LLM API（你提供的 key，存仓库 Secret）。没配 key 时自动降级为规则模板文案。

前端 `index.html` 字段兼容原有结构（`hotspots` / `posts` / `build` / `cycle`），基本不用改。

## 你需要做的（一次性）
1. **建仓库**：GitHub 新建一个**私有**仓库（如 `ent-auto`），把本目录全部内容推上去（含 `.github/`）。
2. **加密钥**：仓库 `Settings → Secrets and variables → Actions → New repository secret`
   - 必填：`LLM_API_KEY` = 你的 DeepSeek 或 OpenRouter key
   - 可选：`LLM_API_URL`（默认 `https://api.deepseek.com/chat/completions`；用 OpenRouter 就填 `https://openrouter.ai/api/v1/chat/completions`）
   - 可选：`LLM_MODEL`（默认 `deepseek-chat`；OpenRouter 可填 `deepseek/deepseek-chat` 等）
3. **开 Pages**：仓库 `Settings → Pages → Source` 选 **main 分支 / (root)**，保存。几分钟后拿到 `https://<你的用户名>.github.io/<仓库名>/`。
4. **开 Actions**：默认开启。首次去 `Actions` 页点 **Run workflow** 手动跑一次验证；之后每小时自动跑。

## 本地调试（可选）
```bash
pip install -r requirements.txt
export LLM_API_KEY=你的key
python scraper.py        # 会生成/更新 data.json
# 本地用任意静态服务器看效果： python -m http.server 然后开 http://localhost:8000
```

## 注意事项
- **抓取源可能需调选择器**：微博/抖音/小红书反爬较强，首次跑若某平台为空属正常，脚本已做"单源失败跳过 + 占位"容错；上线后按运行日志微调 `scraper.py` 里的解析逻辑即可。
- **Pollinations 偶尔慢/失败**：图片是远程 URL，失败时前端显示裂图，下一轮会刷新；不影响热点列表。
- **配额**：私有仓库 Actions 免费 2000 分钟/月，每小时约 2 分钟 ≈ 1440 分钟，够用。
- 旧 CloudStudio 链接可并行保留或下线，互不干扰。
