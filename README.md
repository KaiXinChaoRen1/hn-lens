# hn-lens

终端版 Hacker News 阅读器，内置 LLM 翻译功能。读 HN 新闻，学英语。

## 特性

- **实时 HN 资讯**：通过 Algolia 公共 API 获取热门新闻和 Ask HN 讨论
- **LLM 翻译**：选中新闻或评论，按 `T` 即可翻译（支持 DeepSeek/OpenAI 兼容 API）
- **翻译缓存**：结果本地缓存，节省 API 调用次数
- **中英混排渲染**：按终端显示宽度换行，中文不超框
- **树形评论**：带缩进引导线的评论树
- **纯键盘操作**：vim 风格导航，无需鼠标
- **安全退出**：Ctrl+C 二次确认，5 秒自动取消

## 数据源

本项目使用 **Algolia Hacker News Search API** 作为数据源：

- **API 地址**：`https://hn.algolia.com/api/v1`
- **文档**：https://hn.algolia.com/api
- **为什么用 Algolia**：HN 官方 Firebase API 在国内网络经常无法访问，Algolia 镜像稳定可用，且支持搜索和全文检索
- **免费公开**：无需 API Key，无调用频率限制
- **可用 Feed**：
  - `front_page` — HN 首页热门
  - `ask_hn` — Ask HN 问答讨论

> 注意：Algolia 不提供 `best` 排序，仅提供 `front_page`、`ask_hn`、`show_hn`、`job` 四个标签。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 复制并编辑配置
cp config.example.json ~/.hn/config.json
vim ~/.hn/config.json  # 填入你的 API Key

# 运行
python hn
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
| `r` | 刷新 Feed |
| `1` / `2` | 切换 Feed（热门 / Ask） |
| `q` | 退出 |

### 翻译弹窗

| 按键 | 功能 |
|------|------|
| `j` / `k` | 滚动翻译结果 |
| `PageUp` / `PageDown` | 快速翻页 |
| `Esc` | 关闭弹窗 |

### 退出确认

| 按键 | 功能 |
|------|------|
| `Ctrl+C`（首次） | 进入退出确认 |
| `y` | 确认退出 |
| `Ctrl+C`（二次） | 确认退出 |
| `n` | 取消退出 |
| 5 秒无操作 | 自动取消，回到正常页面 |

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

支持任何 OpenAI 兼容的 API：DeepSeek、OpenAI、Ollama、硅基流动等。

## 依赖

- Python 3.10+
- `requests` 库
- 支持 256 色的终端

## 许可证

MIT
