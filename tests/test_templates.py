from pathlib import Path

from waverly.templates import TemplateManager, build_basic_template


def test_create_and_list_templates(tmp_path):
    manager = TemplateManager(tmp_path)
    body = build_basic_template(
        template_id="demo",
        name="Demo",
        severity="medium",
        method="GET",
        path="/health",
        matcher_words=["ok"],
    )
    manager.create_template("Demo", "medium", ["web"], body, template_id="demo")
    templates = manager.list_templates()
    assert len(templates) == 1
    assert templates[0].template_id == "demo"


def test_save_template_updates_content(tmp_path):
    manager = TemplateManager(tmp_path)
    body = build_basic_template("demo", "Demo", "medium", "GET", "/", ["ok"])
    manager.create_template("Demo", "medium", ["web"], body, template_id="demo")
    new_body = body.replace("ok", "alive")
    manager.save_template("demo", new_body)
    loaded = manager.load_template("demo")
    assert "alive" in loaded


def test_import_templates_skips_duplicates(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    manager = TemplateManager(target)
    body = build_basic_template("demo", "Demo", "medium", "GET", "/", ["ok"])
    (source / "demo.yaml").write_text(body, encoding="utf-8")
    imported = manager.import_templates(source)
    assert len(imported) == 1
    imported_again = manager.import_templates(source)
    assert len(imported_again) == 0


