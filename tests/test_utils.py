from pathlib import Path

from xml.etree import ElementTree as ET
from zipfile import ZipFile

from waverly.nuclei import NucleiTargetResult
from waverly.utils import export_results_to_excel


def test_export_results_to_excel(tmp_path):
    results = [
        NucleiTargetResult(
            template_id="demo",
            matched_at="2023-01-01T00:00:00Z",
            info={"name": "Demo", "severity": "medium", "description": "test"},
            raw={"host": "https://example.com"},
        )
    ]
    output = tmp_path / "results.xlsx"
    export_results_to_excel(results, output)
    assert output.exists()
    with ZipFile(output) as archive:
        content = archive.read("xl/worksheets/sheet1.xml")
    root = ET.fromstring(content)
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows = root.find("x:sheetData", ns).findall("x:row", ns)
    assert len(rows) == 2
    second_row_cells = rows[1].findall("x:c", ns)
    assert second_row_cells[0].find("x:is/x:t", ns).text == "demo"

