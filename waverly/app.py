from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from .config import UserConfig, load_config, save_config
from .fofa import FofaClient, FofaError, FofaResult, RequestError
from .nuclei import NucleiTask
from .tasks import TaskManager
from .templates import TemplateError, TemplateManager, TemplateMetadata, build_basic_template
from .utils import export_results_to_excel, format_timestamp, write_table_to_excel


class WaverlyApp(tk.Tk):
    """Main Tkinter GUI application."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Waverly - FOFA & Nuclei Orchestrator")
        self.geometry("1280x840")
        self.minsize(1100, 720)

        self.config_data: UserConfig = load_config()
        self.template_manager = TemplateManager(self.config_data.templates_dir)
        self.task_manager = TaskManager()
        self.task_manager.add_listener(self._schedule_task_update)

        self.fofa_client: Optional[FofaClient] = None
        self._fofa_results: List[FofaResult] = []
        self._selected_task: Optional[NucleiTask] = None
        self._tasks_cache: dict[str, NucleiTask] = {}
        self._template_cache: List[TemplateMetadata] = []

        self._build_ui()
        self._refresh_template_list()
        self._load_settings_into_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.dashboard_frame = ttk.Frame(self.notebook)
        self.templates_frame = ttk.Frame(self.notebook)
        self.settings_frame = ttk.Frame(self.notebook)

        self.notebook.add(self.dashboard_frame, text="资产与扫描")
        self.notebook.add(self.templates_frame, text="模板管理")
        self.notebook.add(self.settings_frame, text="系统设置")

        self._build_dashboard()
        self._build_templates_tab()
        self._build_settings_tab()

    def _build_dashboard(self) -> None:
        container = ttk.Panedwindow(self.dashboard_frame, orient=tk.HORIZONTAL)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_panel = ttk.Frame(container)
        right_panel = ttk.Frame(container)
        container.add(left_panel, weight=3)
        container.add(right_panel, weight=2)

        self._build_fofa_section(left_panel)
        self._build_scan_section(left_panel)
        self._build_task_section(right_panel)

    def _build_fofa_section(self, parent: ttk.Frame) -> None:
        frame = ttk.Labelframe(parent, text="FOFA 资产搜索")
        frame.pack(fill=tk.BOTH, expand=False, pady=(0, 10))

        query_row = ttk.Frame(frame)
        query_row.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(query_row, text="查询语句:").pack(side=tk.LEFT)
        self.fofa_query_var = tk.StringVar()
        query_entry = ttk.Entry(query_row, textvariable=self.fofa_query_var)
        query_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))

        ttk.Label(query_row, text="返回数量:").pack(side=tk.LEFT)
        self.fofa_size_var = tk.IntVar(value=self.config_data.default_query_size)
        size_spin = ttk.Spinbox(
            query_row,
            from_=1,
            textvariable=self.fofa_size_var,
            width=6,
        )
        size_spin.pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(query_row, text="执行查询", command=self.execute_fofa_query).pack(side=tk.LEFT, padx=5)

        fields_row = ttk.Frame(frame)
        fields_row.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(fields_row, text="字段 (逗号分隔):").pack(side=tk.LEFT)
        self.fofa_fields_var = tk.StringVar(value=",".join(self.config_data.fofa_fields))
        fields_entry = ttk.Entry(fields_row, textvariable=self.fofa_fields_var)
        fields_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        ttk.Button(fields_row, text="保存字段", command=self._update_fofa_fields).pack(side=tk.LEFT)

        columns = self.config_data.fofa_fields
        self.fofa_tree = ttk.Treeview(frame, columns=columns, show="headings", height=7)
        for column in columns:
            self.fofa_tree.heading(column, text=column)
            width = 220 if column == "url" else 120
            self.fofa_tree.column(column, width=width, stretch=True)
        self.fofa_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))

        action_row = ttk.Frame(frame)
        action_row.pack(fill=tk.X, padx=10, pady=(0, 5))
        ttk.Button(action_row, text="添加选中到扫描目标", command=self._append_selected_to_targets).pack(side=tk.LEFT)
        ttk.Button(action_row, text="导入全部结果", command=self._append_all_to_targets).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_row, text="导出结果为Excel", command=self._export_fofa_results).pack(side=tk.LEFT, padx=5)

    def _build_scan_section(self, parent: ttk.Frame) -> None:
        frame = ttk.Labelframe(parent, text="Nuclei 扫描配置")
        frame.pack(fill=tk.BOTH, expand=True)

        upper = ttk.Frame(frame)
        upper.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        ttk.Label(upper, text="扫描目标 (一行一个)").pack(anchor=tk.W)
        self.targets_text = tk.Text(upper, height=6)
        self.targets_text.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        template_frame = ttk.Frame(upper)
        template_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        ttk.Label(template_frame, text="选择模板").pack(anchor=tk.W)
        columns = ("severity", "tags")
        self.template_tree = ttk.Treeview(template_frame, columns=columns, show="headings", selectmode="extended", height=6)
        self.template_tree.heading("severity", text="等级")
        self.template_tree.heading("tags", text="标签")
        self.template_tree.column("severity", width=80, anchor=tk.CENTER)
        self.template_tree.column("tags", width=200, anchor=tk.W)
        self.template_tree.pack(fill=tk.BOTH, expand=True)

        options_frame = ttk.Frame(frame)
        options_frame.pack(fill=tk.X, padx=10, pady=5)

        self.rate_limit_var = tk.IntVar(value=self.config_data.nuclei_rate_limit)
        self.concurrency_var = tk.IntVar(value=self.config_data.nuclei_concurrency)
        self.severity_var = tk.StringVar(value="")
        self.dnslog_var = tk.StringVar(value=self.config_data.dnslog_server)
        self.proxy_var = tk.StringVar(value=self.config_data.proxy.http or "")

        ttk.Label(options_frame, text="速率限制").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(options_frame, from_=1, to=1000, textvariable=self.rate_limit_var, width=8).grid(row=0, column=1, padx=5)
        ttk.Label(options_frame, text="并发").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(options_frame, from_=1, to=500, textvariable=self.concurrency_var, width=8).grid(row=0, column=3, padx=5)
        ttk.Label(options_frame, text="等级过滤").grid(row=0, column=4, sticky="w")
        ttk.Combobox(options_frame, values=["", "info", "low", "medium", "high", "critical"], textvariable=self.severity_var, width=10).grid(row=0, column=5, padx=5)

        ttk.Label(options_frame, text="DNSLOG 服务").grid(row=1, column=0, sticky="w", pady=(5, 0))
        ttk.Entry(options_frame, textvariable=self.dnslog_var, width=25).grid(row=1, column=1, padx=5, pady=(5, 0))
        ttk.Label(options_frame, text="代理").grid(row=1, column=2, sticky="w", pady=(5, 0))
        ttk.Entry(options_frame, textvariable=self.proxy_var, width=25).grid(row=1, column=3, columnspan=3, sticky="we", padx=5, pady=(5, 0))

        button_row = ttk.Frame(frame)
        button_row.pack(fill=tk.X, padx=10, pady=(0, 5))
        ttk.Button(button_row, text="启动扫描", command=self._start_scan).pack(side=tk.LEFT)
        ttk.Button(button_row, text="停止扫描", command=self._stop_selected_task).pack(side=tk.LEFT, padx=5)

    def _build_task_section(self, parent: ttk.Frame) -> None:
        frame = ttk.Labelframe(parent, text="扫描任务与结果")
        frame.pack(fill=tk.BOTH, expand=True)

        columns = ("name", "status", "progress", "results", "started", "finished")
        self.task_tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse", height=10)
        self.task_tree.heading("name", text="任务名称")
        self.task_tree.heading("status", text="状态")
        self.task_tree.heading("progress", text="进度")
        self.task_tree.heading("results", text="命中数量")
        self.task_tree.heading("started", text="开始时间")
        self.task_tree.heading("finished", text="结束时间")
        self.task_tree.column("name", width=140)
        self.task_tree.column("status", width=80, anchor=tk.CENTER)
        self.task_tree.column("progress", width=70, anchor=tk.CENTER)
        self.task_tree.column("results", width=80, anchor=tk.CENTER)
        self.task_tree.column("started", width=140)
        self.task_tree.column("finished", width=140)
        self.task_tree.bind("<<TreeviewSelect>>", self._on_task_selected)
        self.task_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        action_row = ttk.Frame(frame)
        action_row.pack(fill=tk.X, padx=10, pady=(0, 5))
        ttk.Button(action_row, text="导出任务结果", command=self._export_task_results).pack(side=tk.LEFT)
        ttk.Button(action_row, text="清理已完成", command=self._clear_finished_tasks).pack(side=tk.LEFT, padx=5)

        ttk.Label(frame, text="扫描结果详情").pack(anchor=tk.W, padx=10)
        columns = ("template", "severity", "matched", "target")
        self.result_tree = ttk.Treeview(frame, columns=columns, show="headings", height=6)
        self.result_tree.heading("template", text="模板")
        self.result_tree.heading("severity", text="等级")
        self.result_tree.heading("matched", text="命中时间")
        self.result_tree.heading("target", text="目标")
        self.result_tree.column("template", width=160)
        self.result_tree.column("severity", width=80, anchor=tk.CENTER)
        self.result_tree.column("matched", width=160)
        self.result_tree.column("target", width=200)
        self.result_tree.bind("<<TreeviewSelect>>", self._on_result_selected)
        self.result_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))

        result_actions = ttk.Frame(frame)
        result_actions.pack(fill=tk.X, padx=10, pady=(0, 5))
        ttk.Button(result_actions, text="查看请求/响应", command=self._show_result_http_details).pack(side=tk.LEFT)

        self.result_detail = tk.Text(frame, height=8)
        self.result_detail.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

    def _build_templates_tab(self) -> None:
        container = ttk.Panedwindow(self.templates_frame, orient=tk.HORIZONTAL)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        list_panel = ttk.Frame(container)
        detail_panel = ttk.Frame(container)
        container.add(list_panel, weight=2)
        container.add(detail_panel, weight=3)

        toolbar = ttk.Frame(list_panel)
        toolbar.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(toolbar, text="刷新", command=self._refresh_template_list).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="导入模板", command=self._import_templates_from_directory).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="删除选中", command=self._delete_selected_template).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="生成模板", command=self._create_template_from_builder).pack(side=tk.LEFT, padx=5)

        self.template_search_var = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=self.template_search_var, width=28)
        search_entry.pack(side=tk.RIGHT, padx=(5, 0))
        search_entry.bind("<Return>", lambda _event: self._on_template_search())
        ttk.Button(toolbar, text="清除", command=self._reset_template_search).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(toolbar, text="搜索", command=self._on_template_search).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Label(toolbar, text="搜索模板").pack(side=tk.RIGHT, padx=(0, 5))

        tree_frame = ttk.Frame(list_panel)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("name", "template_id", "severity", "author", "tags", "description")
        self.manage_template_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self.manage_template_tree.heading("name", text="模板名称")
        self.manage_template_tree.heading("template_id", text="模板ID")
        self.manage_template_tree.heading("severity", text="等级")
        self.manage_template_tree.heading("author", text="作者")
        self.manage_template_tree.heading("tags", text="标签")
        self.manage_template_tree.heading("description", text="描述")
        self.manage_template_tree.column("name", width=220, anchor=tk.W)
        self.manage_template_tree.column("template_id", width=180, anchor=tk.W)
        self.manage_template_tree.column("severity", width=80, anchor=tk.CENTER)
        self.manage_template_tree.column("author", width=120, anchor=tk.W)
        self.manage_template_tree.column("tags", width=200, anchor=tk.W)
        self.manage_template_tree.column("description", width=260, anchor=tk.W)
        self.manage_template_tree.bind("<<TreeviewSelect>>", self._on_manage_template_selected)

        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.manage_template_tree.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.manage_template_tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.manage_template_tree.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.manage_template_tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.template_notebook = ttk.Notebook(detail_panel)
        self.template_notebook.pack(fill=tk.BOTH, expand=True)

        self.template_editor_tab = ttk.Frame(self.template_notebook)
        self.template_builder_tab = ttk.Frame(self.template_notebook)
        self.template_notebook.add(self.template_editor_tab, text="模板编辑")
        self.template_notebook.add(self.template_builder_tab, text="POC 生成器")

        editor_split = ttk.Panedwindow(self.template_editor_tab, orient=tk.HORIZONTAL)
        editor_split.pack(fill=tk.BOTH, expand=True)

        editor_panel = ttk.Frame(editor_split)
        metadata_panel = ttk.Frame(editor_split, padding=10)
        editor_split.add(editor_panel, weight=3)
        editor_split.add(metadata_panel, weight=2)

        editor_controls = ttk.Frame(editor_panel)
        editor_controls.pack(fill=tk.X, padx=10, pady=(10, 5))
        ttk.Label(editor_controls, text="主题").pack(side=tk.LEFT)
        self.editor_theme_var = tk.StringVar(value="light")
        theme_box = ttk.Combobox(editor_controls, values=["light", "dark"], textvariable=self.editor_theme_var, width=8)
        theme_box.pack(side=tk.LEFT, padx=5)
        theme_box.bind("<<ComboboxSelected>>", lambda _event: self._apply_editor_theme())

        ttk.Label(editor_controls, text="字体大小").pack(side=tk.LEFT)
        self.editor_font_size = tk.IntVar(value=12)
        font_spin = ttk.Spinbox(editor_controls, from_=8, to=22, textvariable=self.editor_font_size, width=5)
        font_spin.pack(side=tk.LEFT)
        font_spin.bind("<FocusOut>", lambda _event: self._apply_editor_theme())

        ttk.Button(editor_controls, text="保存模板", command=self._save_template_changes).pack(side=tk.RIGHT)

        editor_text_frame = ttk.Frame(editor_panel)
        editor_text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.editor_text = tk.Text(editor_text_frame, wrap=tk.NONE)
        self.editor_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        editor_y_scroll = ttk.Scrollbar(editor_text_frame, orient=tk.VERTICAL, command=self.editor_text.yview)
        editor_y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        editor_x_scroll = ttk.Scrollbar(editor_panel, orient=tk.HORIZONTAL, command=self.editor_text.xview)
        editor_x_scroll.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.editor_text.configure(yscrollcommand=editor_y_scroll.set, xscrollcommand=editor_x_scroll.set)

        self.template_name_var = tk.StringVar()
        self.template_id_var = tk.StringVar()
        self.template_severity_var = tk.StringVar()
        self.template_author_var = tk.StringVar()
        self.template_tags_var = tk.StringVar()
        self.template_path_var = tk.StringVar()
        self.template_description_var = tk.StringVar()

        info_frame = ttk.LabelFrame(metadata_panel, text="基础信息")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(info_frame, text="名称").grid(row=0, column=0, sticky="w", padx=5, pady=4)
        ttk.Label(info_frame, textvariable=self.template_name_var).grid(row=0, column=1, sticky="w", padx=5, pady=4)
        ttk.Label(info_frame, text="等级").grid(row=0, column=2, sticky="w", padx=5, pady=4)
        ttk.Label(info_frame, textvariable=self.template_severity_var).grid(row=0, column=3, sticky="w", padx=5, pady=4)

        ttk.Label(info_frame, text="模板 ID").grid(row=1, column=0, sticky="w", padx=5, pady=4)
        ttk.Label(info_frame, textvariable=self.template_id_var).grid(row=1, column=1, sticky="w", padx=5, pady=4)
        ttk.Label(info_frame, text="作者").grid(row=1, column=2, sticky="w", padx=5, pady=4)
        ttk.Label(info_frame, textvariable=self.template_author_var).grid(row=1, column=3, sticky="w", padx=5, pady=4)

        info_frame.columnconfigure(1, weight=1)
        info_frame.columnconfigure(3, weight=1)

        tags_frame = ttk.LabelFrame(metadata_panel, text="标签")
        tags_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(tags_frame, textvariable=self.template_tags_var, wraplength=260, justify=tk.LEFT).pack(anchor=tk.W, padx=5, pady=4)

        path_frame = ttk.LabelFrame(metadata_panel, text="路径")
        path_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(path_frame, textvariable=self.template_path_var, wraplength=260, justify=tk.LEFT).pack(anchor=tk.W, padx=5, pady=4)

        description_frame = ttk.LabelFrame(metadata_panel, text="描述")
        description_frame.pack(fill=tk.BOTH, expand=True)
        self.template_description_label = ttk.Label(
            description_frame,
            textvariable=self.template_description_var,
            wraplength=260,
            justify=tk.LEFT,
        )
        self.template_description_label.pack(fill=tk.BOTH, expand=True, padx=5, pady=4)

        builder_container = ttk.Panedwindow(self.template_builder_tab, orient=tk.HORIZONTAL)
        builder_container.pack(fill=tk.BOTH, expand=True)

        builder_form = ttk.Frame(builder_container, padding=10)
        builder_preview = ttk.Frame(builder_container, padding=10)
        builder_container.add(builder_form, weight=2)
        builder_container.add(builder_preview, weight=3)

        self.builder_id = tk.StringVar()
        self.builder_name = tk.StringVar()
        self.builder_severity = tk.StringVar(value="medium")
        self.builder_method = tk.StringVar(value="GET")
        self.builder_path = tk.StringVar(value="/")
        self.builder_words = tk.StringVar(value="success")
        self.builder_use_raw = tk.BooleanVar(value=False)

        basic_frame = ttk.LabelFrame(builder_form, text="模板信息")
        basic_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(basic_frame, text="模板 ID").grid(row=0, column=0, sticky="w", padx=5, pady=4)
        ttk.Entry(basic_frame, textvariable=self.builder_id, width=24).grid(row=0, column=1, sticky="we", padx=5, pady=4)
        ttk.Label(basic_frame, text="名称").grid(row=1, column=0, sticky="w", padx=5, pady=4)
        ttk.Entry(basic_frame, textvariable=self.builder_name, width=24).grid(row=1, column=1, sticky="we", padx=5, pady=4)
        ttk.Label(basic_frame, text="等级").grid(row=2, column=0, sticky="w", padx=5, pady=4)
        ttk.Combobox(basic_frame, values=["info", "low", "medium", "high", "critical"], textvariable=self.builder_severity, width=22).grid(row=2, column=1, sticky="we", padx=5, pady=4)
        basic_frame.columnconfigure(1, weight=1)

        http_frame = ttk.LabelFrame(builder_form, text="HTTP 配置")
        http_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(http_frame, text="方法").grid(row=0, column=0, sticky="w", padx=5, pady=4)
        ttk.Combobox(http_frame, values=["GET", "POST", "PUT", "DELETE", "PATCH"], textvariable=self.builder_method, width=18).grid(row=0, column=1, sticky="we", padx=5, pady=4)
        ttk.Label(http_frame, text="路径").grid(row=1, column=0, sticky="w", padx=5, pady=4)
        ttk.Entry(http_frame, textvariable=self.builder_path, width=24).grid(row=1, column=1, sticky="we", padx=5, pady=4)
        ttk.Label(http_frame, text="匹配关键词").grid(row=2, column=0, sticky="w", padx=5, pady=4)
        ttk.Entry(http_frame, textvariable=self.builder_words, width=24).grid(row=2, column=1, sticky="we", padx=5, pady=4)

        raw_toggle = ttk.Checkbutton(http_frame, text="启用 Raw 请求编辑", variable=self.builder_use_raw, command=self._toggle_builder_raw)
        raw_toggle.grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=(10, 4))

        self.builder_raw_text = tk.Text(http_frame, height=12, wrap=tk.NONE, state=tk.DISABLED)
        self.builder_raw_text.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=5, pady=(0, 5))
        raw_y_scroll = ttk.Scrollbar(http_frame, orient=tk.VERTICAL, command=self.builder_raw_text.yview)
        raw_y_scroll.grid(row=4, column=2, sticky="ns", pady=(0, 5))
        raw_x_scroll = ttk.Scrollbar(http_frame, orient=tk.HORIZONTAL, command=self.builder_raw_text.xview)
        raw_x_scroll.grid(row=5, column=0, columnspan=2, sticky="ew", padx=5)
        self.builder_raw_text.configure(yscrollcommand=raw_y_scroll.set, xscrollcommand=raw_x_scroll.set)
        http_frame.columnconfigure(1, weight=1)
        http_frame.rowconfigure(4, weight=1)

        builder_actions = ttk.Frame(builder_form)
        builder_actions.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(builder_actions, text="生成模板并保存", command=self._create_template_from_builder).pack(side=tk.LEFT)
        ttk.Button(builder_actions, text="加载到编辑器", command=self._build_template).pack(side=tk.RIGHT)

        preview_frame = ttk.LabelFrame(builder_preview, text="生成预览")
        preview_frame.pack(fill=tk.BOTH, expand=True)
        self.builder_preview_text = tk.Text(preview_frame, wrap=tk.NONE)
        self.builder_preview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        preview_y_scroll = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.builder_preview_text.yview)
        preview_y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        preview_x_scroll = ttk.Scrollbar(builder_preview, orient=tk.HORIZONTAL, command=self.builder_preview_text.xview)
        preview_x_scroll.pack(fill=tk.X, pady=(0, 10))
        self.builder_preview_text.configure(yscrollcommand=preview_y_scroll.set, xscrollcommand=preview_x_scroll.set)
        self.builder_preview_text.configure(state=tk.DISABLED)

        self._apply_editor_theme()

    def _build_settings_tab(self) -> None:
        frame = ttk.Frame(self.settings_frame)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        fofa_frame = ttk.Labelframe(frame, text="FOFA 认证")
        fofa_frame.pack(fill=tk.X, pady=5)
        ttk.Label(fofa_frame, text="邮箱").grid(row=0, column=0, sticky="w")
        self.setting_email = tk.StringVar()
        ttk.Entry(fofa_frame, textvariable=self.setting_email, width=30).grid(row=0, column=1, padx=5, pady=2)
        ttk.Label(fofa_frame, text="API Key").grid(row=0, column=2, sticky="w")
        self.setting_key = tk.StringVar()
        ttk.Entry(fofa_frame, textvariable=self.setting_key, width=50, show="*").grid(row=0, column=3, padx=5, pady=2)

        nuclei_frame = ttk.Labelframe(frame, text="Nuclei 设置")
        nuclei_frame.pack(fill=tk.X, pady=5)
        ttk.Label(nuclei_frame, text="Nuclei 路径").grid(row=0, column=0, sticky="w")
        self.setting_binary = tk.StringVar()
        ttk.Entry(nuclei_frame, textvariable=self.setting_binary, width=40).grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(nuclei_frame, text="浏览", command=self._choose_binary).grid(row=0, column=2, padx=5)

        ttk.Label(nuclei_frame, text="默认速率").grid(row=1, column=0, sticky="w")
        self.setting_rate = tk.IntVar()
        ttk.Spinbox(nuclei_frame, from_=1, to=1000, textvariable=self.setting_rate, width=8).grid(row=1, column=1, sticky="w", padx=5)
        ttk.Label(nuclei_frame, text="默认并发").grid(row=1, column=2, sticky="w")
        self.setting_concurrency = tk.IntVar()
        ttk.Spinbox(nuclei_frame, from_=1, to=500, textvariable=self.setting_concurrency, width=8).grid(row=1, column=3, sticky="w", padx=5)

        dns_frame = ttk.Labelframe(frame, text="DNSLOG 与代理")
        dns_frame.pack(fill=tk.X, pady=5)
        ttk.Label(dns_frame, text="DNSLOG 服务").grid(row=0, column=0, sticky="w")
        self.setting_dnslog = tk.StringVar()
        ttk.Entry(dns_frame, textvariable=self.setting_dnslog, width=40).grid(row=0, column=1, padx=5, pady=2)
        ttk.Label(dns_frame, text="HTTP 代理").grid(row=1, column=0, sticky="w")
        self.setting_http_proxy = tk.StringVar()
        ttk.Entry(dns_frame, textvariable=self.setting_http_proxy, width=40).grid(row=1, column=1, padx=5, pady=2)
        ttk.Label(dns_frame, text="HTTPS 代理").grid(row=1, column=2, sticky="w")
        self.setting_https_proxy = tk.StringVar()
        ttk.Entry(dns_frame, textvariable=self.setting_https_proxy, width=40).grid(row=1, column=3, padx=5, pady=2)
        ttk.Label(dns_frame, text="SOCKS5 代理").grid(row=2, column=0, sticky="w")
        self.setting_socks_proxy = tk.StringVar()
        ttk.Entry(dns_frame, textvariable=self.setting_socks_proxy, width=40).grid(row=2, column=1, padx=5, pady=2)

        template_frame = ttk.Labelframe(frame, text="模板存储")
        template_frame.pack(fill=tk.X, pady=5)
        ttk.Label(template_frame, text="目录").grid(row=0, column=0, sticky="w")
        self.setting_templates_dir = tk.StringVar()
        ttk.Entry(template_frame, textvariable=self.setting_templates_dir, width=60).grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(template_frame, text="选择", command=self._choose_templates_dir).grid(row=0, column=2, padx=5)

        ttk.Button(frame, text="保存设置", command=self._save_settings).pack(anchor=tk.E, pady=10)

    # ------------------------------------------------------------------ FOFA
    def _update_fofa_fields(self) -> None:
        fields = [field.strip() for field in self.fofa_fields_var.get().split(",") if field.strip()]
        self.config_data.fofa_fields = fields
        save_config(self.config_data)
        self._refresh_fofa_columns()
        messagebox.showinfo("提示", "字段已更新")

    def _refresh_fofa_columns(self) -> None:
        columns = self.config_data.fofa_fields
        self.fofa_tree.config(columns=columns)
        for column in columns:
            self.fofa_tree.heading(column, text=column)
            width = 220 if column == "url" else 120
            self.fofa_tree.column(column, width=width, stretch=True)

    def execute_fofa_query(self) -> None:
        expression = self.fofa_query_var.get().strip()
        if not expression:
            messagebox.showwarning("提示", "请输入查询语句")
            return

        try:
            self.fofa_client = FofaClient(
                self.setting_email.get() or self.config_data.fofa_email,
                self.setting_key.get() or self.config_data.fofa_key,
                verify_ssl=self.config_data.verify_ssl,
                timeout=self.config_data.request_timeout,
            )
        except ValueError:
            messagebox.showerror("错误", "请先在设置中配置 FOFA 凭据")
            return

        try:
            results = self.fofa_client.search(
                expression,
                page=1,
                size=self.fofa_size_var.get(),
                fields=self.config_data.fofa_fields,
            )
        except (FofaError, RequestError, ValueError) as exc:
            messagebox.showerror("FOFA 查询失败", str(exc))
            return

        self._fofa_results = results
        self.fofa_tree.delete(*self.fofa_tree.get_children())

        if not results:
            messagebox.showinfo("提示", "未查询到任何资产")
            return

        for idx, result in enumerate(results):
            row = [result.get(column, "") for column in self.config_data.fofa_fields]
            self.fofa_tree.insert("", tk.END, iid=str(idx), values=row)

    def _append_selected_to_targets(self) -> None:
        selected = self.fofa_tree.selection()
        indices: List[int] = []
        for item in selected:
            try:
                indices.append(int(item))
            except (ValueError, TypeError):
                continue
        urls = self._collect_urls_by_indices(indices)
        if not urls:
            messagebox.showinfo("提示", "请选择至少一个包含 URL 的结果")
            return
        self._append_urls_to_targets(urls)

    def _append_all_to_targets(self) -> None:
        urls = self._collect_urls_by_indices(list(range(len(self._fofa_results))))
        if not urls:
            messagebox.showinfo("提示", "当前结果集中未发现 URL")
            return
        self._append_urls_to_targets(urls)

    def _collect_urls_by_indices(self, indices: List[int]) -> List[str]:
        urls: List[str] = []
        seen: set[str] = set()
        for idx in indices:
            if idx < 0:
                continue
            try:
                result = self._fofa_results[idx]
            except IndexError:
                continue
            url = result.get("url")
            if not url:
                continue
            url_str = str(url).strip()
            if url_str and url_str not in seen:
                urls.append(url_str)
                seen.add(url_str)
        return urls

    def _append_urls_to_targets(self, urls: List[str]) -> None:
        existing = [line.strip() for line in self.targets_text.get("1.0", tk.END).splitlines() if line.strip()]
        combined: List[str] = []
        seen = set()
        for item in existing + urls:
            if item and item not in seen:
                combined.append(item)
                seen.add(item)
        self.targets_text.delete("1.0", tk.END)
        self.targets_text.insert(tk.END, "\n".join(combined))

    def _export_fofa_results(self) -> None:
        if not self._fofa_results:
            messagebox.showwarning("提示", "当前没有 FOFA 结果")
            return
        file_path = filedialog.asksaveasfilename(
            title="导出 FOFA 结果",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if not file_path:
            return
        rows = [
            [result.get(field, "") for field in self.config_data.fofa_fields]
            for result in self._fofa_results
        ]
        try:
            write_table_to_excel(self.config_data.fofa_fields, rows, Path(file_path))
            messagebox.showinfo("提示", "导出成功")
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

    # ------------------------------------------------------------------ Scan
    def _start_scan(self) -> None:
        targets = [line.strip() for line in self.targets_text.get("1.0", tk.END).splitlines() if line.strip()]
        if not targets:
            messagebox.showwarning("提示", "请输入扫描目标")
            return

        selected_templates = [self.template_tree.item(item, "text") for item in self.template_tree.selection()]
        if not selected_templates:
            messagebox.showwarning("提示", "请选择至少一个模板")
            return

        severity = self.severity_var.get() or None
        task_name = f"Task-{len(self._tasks_cache) + 1}"
        task = self.task_manager.create_task(
            name=task_name,
            targets=targets,
            templates=selected_templates,
            binary=self.config_data.nuclei_binary,
            rate_limit=self.rate_limit_var.get(),
            concurrency=self.concurrency_var.get(),
            severity=severity,
            dnslog_server=self.dnslog_var.get() or None,
            proxy=self.proxy_var.get() or None,
        )
        self._tasks_cache[task.identifier] = task
        messagebox.showinfo("提示", f"任务 {task.name} 已启动")

    def _schedule_task_update(self, task: NucleiTask) -> None:
        self.after(0, lambda: self._on_task_update(task))

    def _on_task_update(self, task: NucleiTask) -> None:
        self._tasks_cache[task.identifier] = task
        if self.task_tree.exists(task.identifier):
            self.task_tree.item(
                task.identifier,
                values=self._task_row(task),
            )
        else:
            self.task_tree.insert("", tk.END, iid=task.identifier, values=self._task_row(task))
        if self._selected_task and self._selected_task.identifier == task.identifier:
            self._selected_task = task
            self._refresh_task_results(task)

    def _task_row(self, task: NucleiTask) -> List[str]:
        return [
            task.name,
            task.status,
            f"{int(task.progress * 100)}%",
            str(len(task.results)),
            format_timestamp(task.started_at),
            format_timestamp(task.finished_at),
        ]

    def _stop_selected_task(self) -> None:
        selected = self.task_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请选择任务")
            return
        task_id = selected[0]
        self.task_manager.stop_task(task_id)
        messagebox.showinfo("提示", "停止指令已发送")

    def _clear_finished_tasks(self) -> None:
        self.task_manager.clear_finished()
        for task_id in list(self._tasks_cache.keys()):
            task = self._tasks_cache[task_id]
            if task.status in {"completed", "error"}:
                self._tasks_cache.pop(task_id)
                if self.task_tree.exists(task_id):
                    self.task_tree.delete(task_id)

    def _export_task_results(self) -> None:
        selected = self.task_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请选择任务")
            return
        task_id = selected[0]
        task = self._tasks_cache.get(task_id)
        if not task:
            messagebox.showerror("错误", "未找到任务信息")
            return
        if not task.results:
            messagebox.showinfo("提示", "该任务尚无结果")
            return
        file_path = filedialog.asksaveasfilename(
            title="导出任务结果",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if not file_path:
            return
        try:
            export_results_to_excel(task.results, Path(file_path))
            messagebox.showinfo("提示", "导出成功")
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

    def _on_task_selected(self, _event: tk.Event) -> None:
        selected = self.task_tree.selection()
        if not selected:
            return
        task_id = selected[0]
        task = self._tasks_cache.get(task_id)
        if task:
            self._selected_task = task
            self._refresh_task_results(task)

    def _refresh_task_results(self, task: NucleiTask) -> None:
        self.result_tree.delete(*self.result_tree.get_children())
        for idx, result in enumerate(task.results):
            info = result.info
            self.result_tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(
                    result.template_id,
                    info.get("severity", ""),
                    result.matched_at,
                    result.raw.get("host", ""),
                ),
            )
        summary = json.dumps(task.results[-1].raw, indent=2, ensure_ascii=False) if task.results else ""
        self.result_detail.delete("1.0", tk.END)
        self.result_detail.insert(tk.END, summary)

    def _on_result_selected(self, _event: tk.Event) -> None:
        if not self._selected_task:
            return
        selection = self.result_tree.selection()
        if not selection:
            return
        idx = int(selection[0])
        try:
            result = self._selected_task.results[idx]
        except IndexError:
            return
        payload = json.dumps(result.raw, indent=2, ensure_ascii=False)
        self.result_detail.delete("1.0", tk.END)
        self.result_detail.insert(tk.END, payload)

    def _show_result_http_details(self) -> None:
        if not self._selected_task:
            messagebox.showinfo("提示", "请先选择一个任务和结果条目")
            return
        selection = self.result_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请选择需要查看的结果")
            return
        try:
            idx = int(selection[0])
        except (ValueError, TypeError):
            messagebox.showerror("错误", "无法解析结果编号")
            return
        try:
            result = self._selected_task.results[idx]
        except IndexError:
            messagebox.showerror("错误", "未找到对应的结果")
            return

        raw_payload = result.raw if isinstance(result.raw, dict) else {}
        request_packet = self._extract_http_packet(raw_payload, ["request", "http-request", "curl-command"])
        response_packet = self._extract_http_packet(raw_payload, ["response", "http-response", "body"])

        if not request_packet and not response_packet:
            messagebox.showinfo("提示", "该结果未包含请求或响应数据")
            return

        dialog = tk.Toplevel(self)
        dialog.title("请求包与响应包")
        dialog.geometry("960x540")
        dialog.transient(self)
        dialog.grab_set()

        paned = ttk.Panedwindow(dialog, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        request_frame = ttk.LabelFrame(paned, text="请求包")
        response_frame = ttk.LabelFrame(paned, text="响应包")
        paned.add(request_frame, weight=1)
        paned.add(response_frame, weight=1)

        request_text = tk.Text(request_frame, wrap=tk.NONE)
        request_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        request_y_scroll = ttk.Scrollbar(request_frame, orient=tk.VERTICAL, command=request_text.yview)
        request_y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        request_x_scroll = ttk.Scrollbar(request_frame, orient=tk.HORIZONTAL, command=request_text.xview)
        request_x_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        request_text.configure(yscrollcommand=request_y_scroll.set, xscrollcommand=request_x_scroll.set)
        request_text.insert(tk.END, request_packet)

        response_text = tk.Text(response_frame, wrap=tk.NONE)
        response_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        response_y_scroll = ttk.Scrollbar(response_frame, orient=tk.VERTICAL, command=response_text.yview)
        response_y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        response_x_scroll = ttk.Scrollbar(response_frame, orient=tk.HORIZONTAL, command=response_text.xview)
        response_x_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        response_text.configure(yscrollcommand=response_y_scroll.set, xscrollcommand=response_x_scroll.set)
        response_text.insert(tk.END, response_packet)

        action_row = ttk.Frame(dialog)
        action_row.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(action_row, text="关闭", command=dialog.destroy).pack(side=tk.RIGHT)

        self._apply_editor_theme_to_widget(request_text)
        self._apply_editor_theme_to_widget(response_text)

    def _extract_http_packet(self, payload: dict, keys: List[str]) -> str:
        for key in keys:
            value = payload.get(key)
            if value:
                return self._format_http_packet(value)
        return ""

    def _format_http_packet(self, value: object) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple)):
            return "\n".join(str(item) for item in value)
        if isinstance(value, dict):
            return json.dumps(value, indent=2, ensure_ascii=False)
        return str(value)

    def _apply_editor_theme_to_widget(self, widget: tk.Text, preserve_state: bool = True) -> None:
        theme = self.editor_theme_var.get()
        font_size = self.editor_font_size.get()
        if theme == "dark":
            background = "#1e1e1e"
            foreground = "#dcdcdc"
        else:
            background = "#ffffff"
            foreground = "#000000"

        previous_state = widget["state"] if preserve_state else tk.NORMAL
        if preserve_state:
            widget.configure(state=tk.NORMAL)

        widget.configure(background=background, foreground=foreground, insertbackground=foreground)
        widget.configure(font=("Courier New", font_size))

        if preserve_state:
            widget.configure(state=previous_state)

    # ---------------------------------------------------------------- Templates
    def _refresh_template_list(self) -> None:
        self.template_tree.delete(*self.template_tree.get_children())
        templates = self.template_manager.list_templates()
        self._template_cache = templates
        for template in templates:
            values = (template.severity, ",".join(template.tags))
            self.template_tree.insert(
                "",
                tk.END,
                iid=template.path.as_posix(),
                text=str(template.path),
                values=values,
            )
        self._apply_template_filter()

    def _apply_template_filter(self) -> None:
        selected = self.manage_template_tree.selection()
        selected_id = selected[0] if selected else None
        self.manage_template_tree.delete(*self.manage_template_tree.get_children())
        query = self.template_search_var.get().strip().lower()

        for template in self._template_cache:
            haystack = " ".join(
                [
                    template.name,
                    template.template_id,
                    template.severity,
                    template.author or "",
                    ",".join(template.tags),
                    template.description or "",
                ]
            ).lower()
            if query and query not in haystack:
                continue

            description = (template.description or "").replace("\n", " ").strip()
            if len(description) > 120:
                description = f"{description[:117]}..."
            values = (
                template.name,
                template.template_id,
                template.severity,
                template.author or "",
                ",".join(template.tags),
                description,
            )
            self.manage_template_tree.insert(
                "",
                tk.END,
                iid=template.path.as_posix(),
                values=values,
            )

        if selected_id and self.manage_template_tree.exists(selected_id):
            self.manage_template_tree.selection_set(selected_id)
            self.manage_template_tree.see(selected_id)
        else:
            self.manage_template_tree.selection_remove(self.manage_template_tree.selection())
            self._clear_template_details()

        if not self.manage_template_tree.get_children():
            self._clear_template_details()

    def _on_template_search(self) -> None:
        self._apply_template_filter()

        # Automatically focus results when filtering down to a single entry.
        children = self.manage_template_tree.get_children()
        if len(children) == 1:
            self.manage_template_tree.selection_set(children[0])
            self.manage_template_tree.see(children[0])
            self._on_manage_template_selected(None)

    def _reset_template_search(self) -> None:
        if self.template_search_var.get():
            self.template_search_var.set("")
        self._apply_template_filter()

    def _on_manage_template_selected(self, _event: Optional[tk.Event]) -> None:
        selection = self.manage_template_tree.selection()
        if not selection:
            return
        template_path = Path(selection[0])
        metadata = self._get_template_metadata_by_path(template_path)
        if metadata:
            self._update_template_info(metadata)
        else:
            self.template_name_var.set(template_path.stem)
            self.template_id_var.set(template_path.stem)
            self.template_path_var.set(str(template_path))
        if hasattr(self, "template_notebook") and hasattr(self, "template_editor_tab"):
            self.template_notebook.select(self.template_editor_tab)
        try:
            content = template_path.read_text(encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("错误", str(exc))
            return
        self.editor_text.delete("1.0", tk.END)
        self.editor_text.insert(tk.END, content)
        self.editor_text.edit_reset()
        self._update_builder_preview(content)

    def _update_template_info(self, metadata: TemplateMetadata) -> None:
        self.template_name_var.set(metadata.name)
        self.template_id_var.set(metadata.template_id)
        self.template_severity_var.set(metadata.severity or "-")
        self.template_author_var.set(metadata.author or "未提供")
        tags = ", ".join(metadata.tags)
        self.template_tags_var.set(tags or "-")
        self.template_path_var.set(str(metadata.path))
        description = (metadata.description or "").strip()
        self.template_description_var.set(description or "无描述")

    def _clear_template_details(self) -> None:
        self.template_name_var.set("")
        self.template_id_var.set("")
        self.template_severity_var.set("")
        self.template_author_var.set("")
        self.template_tags_var.set("")
        self.template_path_var.set("")
        self.template_description_var.set("")
        self._update_builder_preview("")

    def _get_template_metadata_by_path(self, template_path: Path) -> Optional[TemplateMetadata]:
        for template in self._template_cache:
            if template.path == template_path:
                return template
        return None

    def _delete_selected_template(self) -> None:
        selection = self.manage_template_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请选择模板")
            return
        template_path = Path(selection[0])
        template_id = template_path.stem
        if messagebox.askyesno("确认", f"确定删除模板 {template_id}?"):
            try:
                self.template_manager.delete_template(template_id)
                self._refresh_template_list()
                self.editor_text.delete("1.0", tk.END)
                self._clear_template_details()
            except TemplateError as exc:
                messagebox.showerror("错误", str(exc))

    def _import_templates_from_directory(self) -> None:
        directory = filedialog.askdirectory(title="选择模板目录")
        if not directory:
            return
        try:
            imported = self.template_manager.import_templates(Path(directory))
            messagebox.showinfo("导入完成", f"成功导入 {len(imported)} 个模板")
            self._refresh_template_list()
        except TemplateError as exc:
            messagebox.showerror("导入失败", str(exc))

    def _save_template_changes(self) -> None:
        selection = self.manage_template_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请选择模板")
            return
        template_path = Path(selection[0])
        content = self.editor_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("提示", "模板内容不能为空")
            return
        template_id = template_path.stem
        try:
            self.template_manager.save_template(template_id, content)
            self._refresh_template_list()
            messagebox.showinfo("提示", "保存成功")
        except TemplateError as exc:
            messagebox.showerror("错误", str(exc))

    def _create_template_from_builder(self) -> None:
        template_id = self.builder_id.get() or f"custom-{len(self.template_manager.list_templates()) + 1}"
        name = self.builder_name.get() or "自定义模板"
        severity = self.builder_severity.get() or "medium"
        method = self.builder_method.get() or "GET"
        path_value = self.builder_path.get() or "/"
        words = [word.strip() for word in self.builder_words.get().split(",") if word.strip()]
        raw_request = self._get_builder_raw_request()
        body = build_basic_template(
            template_id,
            name,
            severity,
            method,
            path_value,
            words,
            raw_request=raw_request,
        )
        try:
            self.template_manager.create_template(name, severity, words, body, template_id=template_id)
        except TemplateError as exc:
            messagebox.showerror("错误", str(exc))
            return
        self._refresh_template_list()
        self.editor_text.delete("1.0", tk.END)
        self.editor_text.insert(tk.END, body)
        self._update_builder_preview(body)
        messagebox.showinfo("提示", "模板已生成")

    def _build_template(self) -> None:
        template_id = self.builder_id.get() or "example"
        name = self.builder_name.get() or "示例模板"
        severity = self.builder_severity.get() or "medium"
        method = self.builder_method.get() or "GET"
        path_value = self.builder_path.get() or "/"
        words = [word.strip() for word in self.builder_words.get().split(",") if word.strip()]
        raw_request = self._get_builder_raw_request()
        body = build_basic_template(
            template_id,
            name,
            severity,
            method,
            path_value,
            words,
            raw_request=raw_request,
        )
        self.editor_text.delete("1.0", tk.END)
        self.editor_text.insert(tk.END, body)
        self._update_builder_preview(body)

    def _toggle_builder_raw(self) -> None:
        state = tk.NORMAL if self.builder_use_raw.get() else tk.DISABLED
        self.builder_raw_text.configure(state=tk.NORMAL)
        if state == tk.DISABLED:
            self.builder_raw_text.delete("1.0", tk.END)
        self.builder_raw_text.configure(state=state)
        self._apply_editor_theme_to_widget(self.builder_raw_text)

    def _get_builder_raw_request(self) -> Optional[str]:
        if not getattr(self, "builder_use_raw", None):
            return None
        if not self.builder_use_raw.get():
            return None
        raw = self.builder_raw_text.get("1.0", tk.END).strip()
        return raw or None

    def _update_builder_preview(self, content: str) -> None:
        if not hasattr(self, "builder_preview_text"):
            return
        previous_state = self.builder_preview_text["state"]
        self.builder_preview_text.configure(state=tk.NORMAL)
        self.builder_preview_text.delete("1.0", tk.END)
        if content:
            self.builder_preview_text.insert(tk.END, content)
        self.builder_preview_text.configure(state=previous_state or tk.NORMAL)

    def _apply_editor_theme(self) -> None:
        self._apply_editor_theme_to_widget(self.editor_text, preserve_state=False)

        if hasattr(self, "builder_preview_text"):
            self._apply_editor_theme_to_widget(self.builder_preview_text)

        if hasattr(self, "builder_raw_text"):
            self._apply_editor_theme_to_widget(self.builder_raw_text)

    # ---------------------------------------------------------------- Settings
    def _load_settings_into_ui(self) -> None:
        self.setting_email.set(self.config_data.fofa_email)
        self.setting_key.set(self.config_data.fofa_key)
        self.setting_binary.set(self.config_data.nuclei_binary)
        self.setting_rate.set(self.config_data.nuclei_rate_limit)
        self.setting_concurrency.set(self.config_data.nuclei_concurrency)
        self.setting_dnslog.set(self.config_data.dnslog_server)
        self.setting_http_proxy.set(self.config_data.proxy.http or "")
        self.setting_https_proxy.set(self.config_data.proxy.https or "")
        self.setting_socks_proxy.set(self.config_data.proxy.socks5 or "")
        self.setting_templates_dir.set(str(self.config_data.templates_dir))

    def _save_settings(self) -> None:
        self.config_data.fofa_email = self.setting_email.get().strip()
        self.config_data.fofa_key = self.setting_key.get().strip()
        self.config_data.nuclei_binary = self.setting_binary.get().strip() or "nuclei"
        self.config_data.nuclei_rate_limit = self.setting_rate.get()
        self.config_data.nuclei_concurrency = self.setting_concurrency.get()
        self.config_data.dnslog_server = self.setting_dnslog.get().strip()
        self.config_data.proxy.http = self.setting_http_proxy.get().strip() or None
        self.config_data.proxy.https = self.setting_https_proxy.get().strip() or None
        self.config_data.proxy.socks5 = self.setting_socks_proxy.get().strip() or None
        templates_dir = Path(self.setting_templates_dir.get()).expanduser()
        self.config_data.templates_dir = templates_dir
        save_config(self.config_data)
        self.template_manager = TemplateManager(templates_dir)
        self._refresh_template_list()
        messagebox.showinfo("提示", "设置已保存")

    def _choose_templates_dir(self) -> None:
        directory = filedialog.askdirectory(title="选择模板目录")
        if directory:
            self.setting_templates_dir.set(directory)

    def _choose_binary(self) -> None:
        binary = filedialog.askopenfilename(title="选择 nuclei 可执行文件")
        if binary:
            self.setting_binary.set(binary)


__all__ = ["WaverlyApp"]

