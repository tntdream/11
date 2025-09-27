from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Iterable, List, Sequence
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from .nuclei import NucleiTargetResult


def format_timestamp(timestamp: float | None) -> str:
    if not timestamp:
        return ""
    return dt.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def export_results_to_excel(results: Iterable[NucleiTargetResult], output: Path) -> Path:
    rows: List[List[str]] = [
        [
            "Template ID",
            "Name",
            "Severity",
            "Target",
            "Matched At",
            "Description",
        ]
    ]
    for result in results:
        info = result.info
        rows.append(
            [
                result.template_id,
                str(info.get("name", "")),
                str(info.get("severity", "")),
                str(result.raw.get("host", "")),
                str(result.matched_at),
                str(info.get("description", "")),
            ]
        )

    return write_table_to_excel(rows[0], rows[1:], output)


def write_table_to_excel(headers: Sequence[str], rows: Iterable[Sequence[str]], output: Path) -> Path:
    data_rows: List[List[str]] = [list(headers)]
    for row in rows:
        data_rows.append([str(value) for value in row])

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml())
        archive.writestr("_rels/.rels", _rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        archive.writestr("xl/styles.xml", _styles_xml())
        archive.writestr("xl/worksheets/sheet1.xml", _sheet_xml(data_rows))
    return output_path


def _content_types_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>
"""


def _rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""


def _workbook_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Nuclei Results" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
"""


def _workbook_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""


def _styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border/></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>
"""


def _sheet_xml(rows: List[List[str]]) -> str:
    header = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><sheetData>"
    )
    body_parts: List[str] = []
    for row_idx, row in enumerate(rows, start=1):
        cells: List[str] = []
        for col_idx, value in enumerate(row, start=1):
            cell_ref = _column_name(col_idx) + str(row_idx)
            cells.append(
                f"<c r=\"{cell_ref}\" t=\"inlineStr\"><is><t>{escape(value)}</t></is></c>"
            )
        body_parts.append(f"<row r=\"{row_idx}\">{''.join(cells)}</row>")
    footer = "</sheetData></worksheet>"
    return header + "".join(body_parts) + footer


def _column_name(index: int) -> str:
    name = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name or "A"


__all__ = ["format_timestamp", "export_results_to_excel", "write_table_to_excel"]

