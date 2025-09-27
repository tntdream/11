# Waverly — FOFA & Nuclei 图形化联动平台

Waverly 是一个面向攻防研究人员的跨平台桌面工具，集成了 FOFA 资产搜索、Nuclei POC 模板管理与批量漏洞验证能力。项目基于 Python + Tkinter 构建，可在 macOS 与 Windows 上直接运行（Linux 支持测试中），并提供配置持久化、实时任务监控、Excel 导出等高级功能。

## 功能特性

- **FOFA API 图形化查询**：通过界面录入查询语句与字段，实时展示资产搜索结果，并支持一键导出。
- **模板生命周期管理**：增删查改 nuclei POC 模板，支持目录导入、重复自动去重与可视化编辑器（主题切换、字体调整）。
- **多任务批量扫描**：同一时间可运行多个任务，支持多目标、多模板组合，实时进度展示与任务停止控制。
- **高级扫描配置**：内置 DNSLOG 地址、速率限制、并发、代理 (HTTP/HTTPS/SOCKS5) 等高级参数调节。
- **请求/响应分析**：扫描结果可查看完整 JSON 数据，快速定位请求头、响应包等细节。
- **POC 向导生成**：使用图形化表单快速构建基础 HTTP POC 并写入模板目录。
- **API/目录测试**：支持填写携带路径的 API 目标，一键加入扫描任务进行验证。
- **配置持久化**：用户偏好（API Key、模板目录、代理设置等）自动保存到本地文件，下次启动直接使用。
- **Excel 导出**：扫描结果与 FOFA 资产均可导出为 `.xlsx` 以便归档或二次分析。

## 运行环境

- Python 3.10+
- 依赖：`requests`（FOFA API 功能需要）
- 开发/测试依赖：`pytest`
- 系统内需预先安装 [Nuclei](https://github.com/projectdiscovery/nuclei) 可执行文件，并在设置页指向其路径。
- FOFA API 需要合法账号与 API Key（可通过环境变量 `WAVERLY_FOFA_EMAIL` 与 `WAVERLY_FOFA_KEY` 预先配置，若界面已保存凭据则优先生效）。

安装依赖：

```bash
pip install -r requirements.txt
```

启动界面：

```bash
python -m waverly
```

若在 Linux 服务器等无图形界面的环境中运行，可先执行：

```bash
python -m waverly --check
```

以确认是否已提供可用的 DISPLAY；如未检测到，将给出友好的提示信息。

首次运行会在用户目录下生成 `~/.waverly/` 目录，用于持久化配置、缓存与模板。可在“系统设置”页调整模板目录后重新加载。

## 代码结构

```
waverly/
├── app.py            # Tkinter 图形界面主程序
├── config.py         # 配置模型、读写与目录初始化
├── fofa.py           # FOFA API 客户端封装
├── nuclei.py         # Nuclei 任务抽象与执行器
├── tasks.py          # 多任务调度与监听
├── templates.py      # 模板管理、导入、快速生成
├── utils.py          # 通用工具（时间格式化、Excel 导出）
└── __main__.py       # 入口，支持 python -m waverly
```

测试位于 `tests/` 目录，包含配置、模板与工具模块的单元测试。

## 常见工作流

1. 在“系统设置”中配置 FOFA 邮箱 & API Key、Nuclei 路径、模板目录与代理（如果已设置 `WAVERLY_FOFA_EMAIL` / `WAVERLY_FOFA_KEY` 环境变量且当前字段为空会自动填充）。
2. 切换至“资产与扫描”页，输入 FOFA dork，查看结果并将选中资产加入目标列表。
3. 选择需要联动的 POC 模板，设置速率、并发、DNSLOG、代理等参数，点击“启动扫描”。
4. 在右侧任务面板实时查看进度、命中情况与原始数据，可随时停止任务或导出为 Excel。
5. 若需新增/修改模板，可在“模板管理”页通过编辑器进行操作，并支持快速 POC 生成。

## 开发与测试

推荐使用 `virtualenv` 或 `conda` 创建隔离环境，完成依赖安装后执行单元测试：

```bash
pytest
```

## 许可协议

本项目使用 MIT License，详情见仓库根目录的 LICENSE 文件（如有）。

