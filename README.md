# hn-lens

[![Tests](https://github.com/KaiXinChaoRen1/hn-lens/actions/workflows/tests.yml/badge.svg)](https://github.com/KaiXinChaoRen1/hn-lens/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-terminal-success)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

一个面向终端的 Hacker News 阅读器，带评论树、正文抽取、LLM 翻译和适合中文用户的阅读体验优化。

`hn-lens` 的目标不是做一个“能跑的 demo”，而是做一个真正能每天打开、快速扫 HN、顺手学英语的终端工具。

## 为什么这个项目值得用

- **终端优先**：纯键盘操作，阅读路径很短，适合开发者日常使用
- **适合中文用户**：内置翻译入口，支持 DeepSeek / OpenAI 兼容 API
- **不只看标题**：支持评论树和文章正文抽取，不必频繁跳浏览器
- **启动更轻**：首页增量加载、短时缓存、分批展示评论，减少等待感
- **不是一次性脚本**：已经有基础自动化回归测试，后续迭代更可控

## 当前状态

这个项目目前已经是一个**可用状态**的终端工具，适合：

- 日常刷 Hacker News 首页和 Ask HN
- 快速看评论、判断帖子是否值得深入读
- 对英文标题、评论、正文做即时翻译
- 在国内网络环境下，用比 HN 官方 Firebase API 更稳的方式获取内容

如果你希望的是一个轻量、直接、可持续改进的 HN 终端客户端，这个项目已经能满足这个定位。

## 功能亮点

- **首页与 Ask HN Feed**：基于 Algolia HN Search API 获取内容
- **增量加载**：首页首批 20 条，继续浏览时自动补载
- **评论树阅读**：支持嵌套评论、分层展示和分批展开
- **正文阅读模式**：提取文章主内容，尽量剔除页面噪音
- **翻译弹窗**：原文与翻译分区显示，支持滚动查看
- **翻译缓存**：避免重复请求，降低 API 成本
- **安全退出**：全局 `Ctrl+C` 二次确认，减少误退出

## 快速开始

```bash
# 1. 克隆仓库
git clone git@github.com:KaiXinChaoRen1/hn-lens.git
cd hn-lens

# 2. 创建虚拟环境并安装依赖
python3.10 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# 3. 配置翻译 API（可选）
cp config.example.json ~/.hn/config.json
vim ~/.hn/config.json

# 4. 运行
python hn
```

如果你已经按项目建议把 `hn` 安装到 `~/.local/bin`，后续直接运行：

```bash
hn
```

## 快捷键

| 按键 | 功能 |
|------|------|
| `j` / `k` | 上 / 下导航 |
| `g` / `G` | 跳到顶部 / 底部 |
| `o` / `Enter` | 打开新闻详情 |
| `c` | 查看评论 |
| `a` | 终端内阅读文章 |
| `u` | 浏览器打开链接 |
| `/` | 搜索新闻 |
| `T` | 翻译选中内容 |
| `r` | 刷新当前 Feed |
| `1` / `2` | 切换 Feed（Top / Ask） |
| `q` | 退出 |

### 翻译弹窗

| 按键 | 功能 |
|------|------|
| `j` / `k` | 滚动翻译内容 |
| `PageUp` / `PageDown` | 快速翻页 |
| `g` / `G` | 跳到顶部 / 底部 |
| `Esc` | 关闭弹窗 |

### 退出确认

| 按键 | 功能 |
|------|------|
| `Ctrl+C`（首次） | 进入退出确认 |
| `Ctrl+C`（再次） | 立即退出 |
| `y` | 确认退出 |
| `n` | 取消退出 |
| 5 秒无操作 | 自动取消 |

## 配置

编辑 `~/.hn/config.json`：

```json
{
  "api_url": "https://api.deepseek.com/v1/chat/completions",
  "api_key": "sk-your-key-here",
  "api_model": "deepseek-chat",
  "prompt_word": "翻译提示词模板（单词）",
  "prompt_item": "翻译提示词模板（全文）"
}
```

支持任何 OpenAI 兼容 API，例如：

- DeepSeek
- OpenAI
- Ollama
- 硅基流动

## 依赖的数据源

本项目当前核心依赖 **Algolia Hacker News Search API**：

- API: `https://hn.algolia.com/api/v1`
- 文档: [hn.algolia.com/api](https://hn.algolia.com/api)
- Demo: [hn.algolia.com](https://hn.algolia.com)
- 上游仓库: [`algolia/hn-search`](https://github.com/algolia/hn-search)

### 为什么选它

- HN 官方 Firebase API 在国内经常不稳定
- Algolia 这套接口更适合搜索、列表和评论浏览
- 无需为本项目单独维护后端

### 需要知道的事实

- 这不是本项目自己控制的服务，而是公共外部依赖
- 官方公开资料没有给出我们可以依赖的 SLA
- 没看到清晰公开的硬性频率限制文档，所以更合理的态度是“公开可访问，但不要高频滥用”
- 上游 `algolia/hn-search` 仓库目前已归档，只读

这意味着：`hn-lens` 目前是一个依赖公共镜像服务的轻量客户端，而不是完全自托管的数据产品。

## 测试

本项目已经带有基础回归测试，用来防止后续修改把关键体验改坏。

本地运行：

```bash
.venv/bin/python -m unittest discover -s tests -v
```

当前测试覆盖包括：

- 首页刷新失败时不清空已有内容
- 搜索模式下的终端兼容性
- 翻译错误结果不进入缓存
- 文章抽取优先正文而不是整页噪音

## GitHub 可见信号

为了让项目首页看起来像一个真的在维护的工具，而不是练手代码，当前仓库首页会尽量传达这几件事：

- 有明确定位：HN 终端阅读器，不是杂项集合
- 有可用功能：新闻、评论、正文、翻译、缓存、增量加载
- 有维护信号：测试、CI、文档、许可证
- 有现实边界：明确说明外部数据依赖和限制

这类项目能不能吸引 star，往往不只是“代码能跑”，而是首页是否能让人快速判断：

1. 这个项目解决什么问题
2. 它现在能不能用
3. 作者有没有持续维护的打算

## 后续还可以继续增强什么

如果你想继续把首页做得更像“真实项目”，优先级最高的通常是：

- 增加终端截图或 GIF
- 增加 “Why this exists” / “Design goals” 小节
- 增加版本发布和 changelog
- 增加 GitHub Release
- 增加 issue template / discussion / roadmap

这些都会比单纯堆技术细节更容易吸引 star。

## 依赖

- Python 3.10+
- `requests`
- `beautifulsoup4`
- `readability-lxml`
- 支持 256 色的终端

## 许可证

MIT
