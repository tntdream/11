from waverly.nuclei import NucleiTask, summarize_results


def test_nuclei_task_command_building(tmp_path):
    template = tmp_path / "demo.yaml"
    template.write_text("id: demo", encoding="utf-8")
    task = NucleiTask(
        name="demo",
        targets=["https://example.com"],
        templates=[template],
        binary="nuclei",
        rate_limit=50,
        concurrency=10,
        severity="medium",
        dnslog_server="dnslog.local",
        proxy="http://127.0.0.1:8080",
    )
    command = task.build_command()
    assert "-t" in command
    assert str(template) in command
    assert "-target" in command
    assert "https://example.com" in command


def test_summarize_results_counts_by_severity():
    results = [
        type("Result", (), {"info": {"severity": "high"}})(),
        type("Result", (), {"info": {"severity": "high"}})(),
        type("Result", (), {"info": {"severity": "medium"}})(),
    ]
    summary = summarize_results(results)
    assert summary["high"] == 2
    assert summary["medium"] == 1

