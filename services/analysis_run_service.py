import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from models.analysis import AnalysisRun, AnalysisResult
from services.export_job_service import export_job_service
from services.export_serializers import (
    build_analysis_export_payload,
    dump_payload_to_json,
    iter_analysis_export_rows,
    serialize_analysis_run,
)
from services.storage_backend import export_storage_backend
from utils.exceptions import ValidationError


class AnalysisRunService:
    def generate_analysis_export(
        self,
        run_id: str,
        organization_id: str,
        export_format: str,
        node_ids: Optional[List[str]] = None,
        analysis_id: Optional[str] = None,
    ) -> tuple[str, int]:
        export_format = (export_format or "").lower()
        if export_format not in {"csv", "json", "excel", "pdf"}:
            raise ValidationError(
                "Unsupported analysis export format. Supported formats are csv, json, excel and pdf."
            )

        run = self.get_run(analysis_id or "", run_id, organization_id) if analysis_id else None
        if not run:
            run = AnalysisRun.objects(id=run_id, organization_id=organization_id).first()
        if not run:
            raise ValidationError("Analysis run not found")

        result_query = AnalysisResult.objects(
            run_id=str(run_id), organization_id=organization_id
        ).order_by("created_at")
        if node_ids:
            node_filter = {str(node_id) for node_id in node_ids}
            result_query = result_query.filter(node_id__in=list(node_filter))

        analysis_path = str(analysis_id or run.analysis_id)
        export_dir = export_storage_backend.base_root / analysis_path / str(run_id)
        export_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        file_path = export_dir / f"analysis_export_{timestamp}.{export_format}"

        if export_format == "json":
            self._write_json_export(file_path, serialize_analysis_run(run), result_query)
        elif export_format == "excel":
            result_list = list(result_query)
            return self.generate_excel_export(run, results=result_list, file_path=file_path)
        elif export_format == "pdf":
            result_list = list(result_query)
            self._write_pdf_export(file_path, build_analysis_export_payload(run, result_list))
        else:
            self._write_csv_export(file_path, iter_analysis_export_rows(run, result_query))

        return str(file_path), file_path.stat().st_size

    def _write_csv_export(self, file_path: Path, rows) -> None:
        import csv

        with file_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "id",
                    "analysis_id",
                    "run_id",
                    "node_id",
                    "organization_id",
                    "output_type",
                    "row_count",
                    "column_definitions",
                    "cached_until",
                    "created_at",
                    "data",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        **row,
                        "data": json.dumps(row["data"], ensure_ascii=False, default=str),
                    }
                )

    def _write_json_export(self, file_path: Path, run_payload: Dict[str, Any], rows) -> None:
        with file_path.open("w", encoding="utf-8") as handle:
            handle.write("{\n")
            handle.write(f'  "run": {dump_payload_to_json(run_payload)},\n')
            handle.write('  "results": [\n')
            first = True
            for row in rows:
                if not first:
                    handle.write(",\n")
                handle.write("    ")
                handle.write(dump_payload_to_json(row).replace("\n", "\n    "))
                first = False
            handle.write("\n  ]\n}\n")

    def generate_excel_export(
        self,
        run: AnalysisRun,
        results: Optional[List[AnalysisResult]] = None,
        file_path: Optional[Path] = None,
    ) -> tuple[str, int]:
        payload = build_analysis_export_payload(
            run, results or self.get_results(str(run.id), str(run.organization_id))
        )
        export_dir = (
            file_path.parent
            if file_path
            else export_storage_backend.base_root
            / str(run.analysis_id)
            / str(run.id)
        )
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        workbook_path = file_path or export_dir / f"analysis_export_{timestamp}.xlsx"

        self._write_minimal_xlsx(
            workbook_path,
            {
                "Run Metadata": [
                    ["field", "value"],
                    *[
                        [
                            field,
                            json.dumps(value, ensure_ascii=False, default=str)
                            if isinstance(value, (dict, list))
                            else value,
                        ]
                        for field, value in payload["run"].items()
                    ],
                ],
                "Node Results": [
                    ["result_id", "node_id", "output_type", "row_count", "data"],
                    *[
                        [
                            row["id"],
                            row["node_id"],
                            row["output_type"],
                            row["row_count"],
                            json.dumps(row["data"], ensure_ascii=False, default=str),
                        ]
                        for row in payload["results"]
                    ],
                ],
            },
        )
        return str(workbook_path), workbook_path.stat().st_size

    def _column_letter(self, index: int) -> str:
        letters = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            letters = chr(65 + remainder) + letters
        return letters or "A"

    def _escape_xml(self, value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    def _sheet_xml(self, rows: List[List[Any]]) -> str:
        xml_rows = []
        for row_idx, row in enumerate(rows, start=1):
            cells = []
            for col_idx, value in enumerate(row, start=1):
                cell_ref = f"{self._column_letter(col_idx)}{row_idx}"
                if value is None:
                    cell = f'<c r="{cell_ref}"/>'
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    cell = f'<c r="{cell_ref}"><v>{value}</v></c>'
                else:
                    text = self._escape_xml(str(value))
                    cell = (
                        f'<c r="{cell_ref}" t="inlineStr">'
                        f"<is><t>{text}</t></is></c>"
                    )
                cells.append(cell)
            xml_rows.append(f"<row r=\"{row_idx}\">{''.join(cells)}</row>")
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"<sheetData>{''.join(xml_rows)}</sheetData>"
            "</worksheet>"
        )

    def _write_minimal_xlsx(self, workbook_path: Path, sheets: Dict[str, List[List[Any]]]) -> None:
        import zipfile

        workbook_path.parent.mkdir(parents=True, exist_ok=True)
        sheet_names = list(sheets.keys())
        workbook_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>"
            + "".join(
                f'<sheet name="{self._escape_xml(name)}" sheetId="{idx}" r:id="rId{idx}"/>'
                for idx, name in enumerate(sheet_names, start=1)
            )
            + "</sheets></workbook>"
        )
        workbook_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{idx}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{idx}.xml"/>'
                for idx in range(1, len(sheet_names) + 1)
            )
            + "</Relationships>"
        )
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{idx}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for idx in range(1, len(sheet_names) + 1)
            )
            + "</Types>"
        )
        root_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            "</Relationships>"
        )
        with zipfile.ZipFile(workbook_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("_rels/.rels", root_rels)
            archive.writestr("xl/workbook.xml", workbook_xml)
            archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
            for idx, sheet_name in enumerate(sheet_names, start=1):
                archive.writestr(f"xl/worksheets/sheet{idx}.xml", self._sheet_xml(sheets[sheet_name]))

    def _pdf_escape(self, value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
            .replace("\r", " ")
            .replace("\n", " ")
        )

    def _write_pdf_export(self, file_path: Path, payload: Dict[str, Any]) -> None:
        lines = [
            "Analysis Export",
            f"Run ID: {payload['run']['id']}",
            f"Analysis ID: {payload['run']['analysis_id']}",
            f"Status: {payload['run']['status']}",
            f"Results: {len(payload['results'])}",
        ]
        for result in payload["results"][:20]:
            lines.extend(
                self._wrap_pdf_text(
                    f"{result['node_id']} | {result['output_type']} | "
                    f"{json.dumps(result['data'], ensure_ascii=False, default=str)}",
                    width=90,
                )
            )

        content_lines = ["BT", "/F1 12 Tf", "72 760 Td", "14 TL"]
        for line in lines:
            safe_line = self._pdf_escape(str(line))[:180]
            content_lines.append(f"({safe_line}) Tj")
            content_lines.append("T*")
        content_lines.append("ET")
        stream = "\n".join(content_lines).encode("latin-1", "replace")

        pdf = bytearray()
        pdf.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

        object_offsets: list[int] = [0]

        def add_object(obj_num: int, body: bytes) -> None:
            object_offsets.append(len(pdf))
            pdf.extend(f"{obj_num} 0 obj\n".encode("ascii"))
            pdf.extend(body)
            if not body.endswith(b"\n"):
                pdf.extend(b"\n")
            pdf.extend(b"endobj\n")

        add_object(1, b"<< /Type /Catalog /Pages 2 0 R >>")
        add_object(2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
        add_object(
            3,
            (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
            ),
        )
        add_object(4, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        content_object = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        )
        add_object(5, content_object)

        xref_start = len(pdf)
        xref = bytearray()
        xref.extend(f"xref\n0 {len(object_offsets)}\n".encode("ascii"))
        xref.extend(b"0000000000 65535 f \n")
        for offset in object_offsets[1:]:
            xref.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        xref.extend(
            (
                "trailer << /Size {size} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".format(
                    size=len(object_offsets), start=xref_start
                )
            ).encode("ascii")
        )
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(bytes(pdf) + bytes(xref))

    def _wrap_pdf_text(self, text: str, width: int = 90) -> List[str]:
        words = str(text).split()
        if not words:
            return [""]
        lines: List[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if len(candidate) > width:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
        return lines

    def create_run(
        self,
        analysis_id: str,
        organization_id: str,
        trigger: str = "on_demand",
        triggered_by: Optional[str] = None,
        celery_task_id: Optional[str] = None,
    ) -> AnalysisRun:
        run = AnalysisRun(
            analysis_id=str(analysis_id),
            organization_id=organization_id,
            trigger=trigger,
            triggered_by=triggered_by,
            celery_task_id=celery_task_id,
            status="running",
        )
        run.save()
        return run

    def finish_run(
        self,
        run: AnalysisRun,
        node_statuses: Dict[str, Dict[str, Any]],
        result_ids: Dict[str, str],
        error_summary: Optional[str] = None,
    ) -> AnalysisRun:
        run.node_statuses = node_statuses
        run.result_ids = result_ids
        run.error_summary = error_summary
        run.status = "failed" if error_summary else "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.save()
        return run

    def record_result(
        self,
        run: AnalysisRun,
        node_id: str,
        analysis_id: str,
        organization_id: str,
        payload: Any,
        output_type: str = "value",
    ) -> AnalysisResult:
        result = AnalysisResult(
            run_id=str(run.id),
            analysis_id=str(analysis_id),
            node_id=str(node_id),
            organization_id=organization_id,
            output_type=output_type,
            data=payload if isinstance(payload, dict) else {"value": payload},
        )
        if isinstance(payload, dict) and "row_count" in payload:
            result.row_count = payload.get("row_count")
        result.save()
        return result

    def list_runs(
        self, analysis_id: str, organization_id: str, limit: int = 20
    ) -> List[AnalysisRun]:
        return list(
            AnalysisRun.objects(
                analysis_id=str(analysis_id), organization_id=organization_id
            )
            .order_by("-created_at")
            .limit(limit)
        )

    def get_run(
        self, analysis_id: str, run_id: str, organization_id: str
    ) -> Optional[AnalysisRun]:
        return AnalysisRun.objects(
            id=run_id, analysis_id=str(analysis_id), organization_id=organization_id
        ).first()

    def get_results(self, run_id: str, organization_id: str) -> List[AnalysisResult]:
        return list(AnalysisResult.objects(run_id=str(run_id), organization_id=organization_id).order_by("created_at"))

    def create_export(
        self,
        analysis_id: str,
        run_id: str,
        organization_id: str,
        created_by: Optional[str],
        export_format: str,
        node_ids: Optional[List[str]] = None,
        file_path: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        status: str = "pending",
        expires_in_days: int = 7,
        queue_generation: bool = False,
    ) -> Any:
        run = AnalysisRun.objects(
            id=str(run_id), analysis_id=str(analysis_id), organization_id=organization_id
        ).first()
        if not run:
            raise ValidationError("Analysis run not found")

        job = export_job_service.create_job(
            analysis_run_id=str(run_id),
            export_format=export_format,
            organization_id=organization_id,
            analysis_id=str(analysis_id),
            status="pending",
            node_ids=node_ids or [],
            idempotency_key=f"{analysis_id}:{run_id}:{export_format}:{created_by or ''}",
            expires_in_days=expires_in_days,
        )

        if file_path:
            effective_status = "pending" if str(status).lower() == "queued" else status
            export_job_service.transition_status(
                job,
                effective_status,
                file_path=file_path,
                file_size_bytes=file_size_bytes,
                last_error=None,
            )
        elif queue_generation:
            from tasks.export_tasks import generate_analysis_export_task

            export_job_service.transition_status(job, "queued")
            generate_analysis_export_task.delay(str(job.id), export_format)
        else:
            generated_path, generated_size = self.generate_analysis_export(
                run_id=run_id,
                organization_id=organization_id,
                export_format=export_format,
                node_ids=node_ids,
                analysis_id=analysis_id,
            )
            export_job_service.attach_file_path(job, generated_path, generated_size)
        return job


analysis_run_service = AnalysisRunService()
