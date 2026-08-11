"""Deterministic HTML, DOCX and PDF rendering for frozen PER manifests."""

import hashlib
import html
import io
import textwrap
import zipfile
from dataclasses import dataclass
from uuid import UUID
from xml.sax.saxutils import escape as xml_escape

from orkp.db.models import EventLog, GeneratedArtifact
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import BaselineValidationError
from orkp.domain.per_draft_models import PERDraftPayload
from orkp.domain.per_draft_service import PERDraftService
from orkp.domain.per_render_models import PER_RENDER_FORMATS, PERRenderResult


_MEDIA_TYPES = {
    "html": "text/html; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}

_SECTION_LABELS = {
    "scientific_validity": "Scientific Validity",
    "analytical_performance": "Analytical Performance",
    "clinical_performance": "Clinical Performance",
}


@dataclass(frozen=True)
class _DocumentBlock:
    style: str
    text: str


class PERRenderService:
    """Render deterministic document bytes exclusively from a frozen PER baseline."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def render(
        self,
        baseline_hex: str,
        render_format: str,
        generated_by_user_id: str,
    ) -> PERRenderResult:
        if render_format not in PER_RENDER_FORMATS:
            raise BaselineValidationError(
                f"Unsupported PER render format '{render_format}'"
            )

        draft = PERDraftService(self.repo).build_draft(baseline_hex)
        blocks = self._document_blocks(draft)
        if render_format == "html":
            content = self._render_html(draft, blocks)
        elif render_format == "docx":
            content = self._render_docx(blocks)
        else:
            content = self._render_pdf(blocks)

        baseline = self._load_baseline(draft.baseline_uuid)
        checksum = hashlib.sha256(content).hexdigest()
        filename = f"per-{draft.baseline_uuid[:8]}.{render_format}"

        try:
            artifact = GeneratedArtifact(
                baseline_uuid=baseline.baseline_uuid,
                artifact_type="per_report",
                format=render_format,
                file_path=None,
                checksum=checksum,
                generated_by=generated_by_user_id,
            )
            self.repo.session.add(artifact)
            self.repo.session.flush()
            self.repo.session.add(
                EventLog(
                    aggregate_type="baseline",
                    aggregate_uuid=baseline.baseline_uuid,
                    event_type="artifact_generated",
                    event_data={
                        "artifact_uuid": UUID(bytes=artifact.artifact_uuid).hex,
                        "artifact_type": artifact.artifact_type,
                        "format": artifact.format,
                        "checksum": checksum,
                        "filename": filename,
                    },
                    actor_user_id=generated_by_user_id,
                )
            )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise

        return PERRenderResult(
            artifact_uuid=UUID(bytes=artifact.artifact_uuid).hex,
            baseline_uuid=draft.baseline_uuid,
            format=render_format,
            media_type=_MEDIA_TYPES[render_format],
            filename=filename,
            checksum_sha256=checksum,
            content=content,
        )

    def _load_baseline(self, baseline_hex: str):
        try:
            baseline_uuid = UUID(baseline_hex).bytes
        except (ValueError, AttributeError, TypeError) as exc:
            raise BaselineValidationError(
                f"Invalid PER baseline UUID format: {baseline_hex}"
            ) from exc
        baseline = self.repo.get_baseline(baseline_uuid)
        if baseline is None:
            raise BaselineValidationError(f"PER baseline {baseline_hex} not found")
        return baseline

    @classmethod
    def _document_blocks(cls, draft: PERDraftPayload) -> list[_DocumentBlock]:
        blocks = [
            _DocumentBlock("title", "Performance Evaluation Report"),
            _DocumentBlock("body", f"Baseline: {draft.baseline_name}"),
            _DocumentBlock("body", f"Baseline UUID: {draft.baseline_uuid}"),
            _DocumentBlock(
                "body",
                f"Product: {draft.product.object_uuid} v{draft.product.object_version}",
            ),
            _DocumentBlock("h1", "Performance Sections"),
        ]

        for section in draft.performance_sections.sections:
            blocks.append(
                _DocumentBlock(
                    "h2",
                    _SECTION_LABELS.get(section.section_type, section.section_type),
                )
            )
            if not section.items:
                blocks.append(_DocumentBlock("body", "No frozen Performance Results."))
                continue
            for item in section.items:
                result = item.performance_result.snapshot
                blocks.append(
                    _DocumentBlock(
                        "h3",
                        f"Result {item.performance_result.object_uuid} "
                        f"v{item.performance_result.object_version}",
                    )
                )
                cls._append_if_present(blocks, "Parameter", result.get("parameter"))
                cls._append_if_present(blocks, "Result", result.get("result_value"))
                cls._append_if_present(blocks, "Unit", result.get("unit"))
                cls._append_if_present(
                    blocks,
                    "Statistical method",
                    result.get("statistical_method"),
                )
                cls._append_if_present(
                    blocks,
                    "Quality",
                    result.get("quality_rating"),
                )
                study = item.study.snapshot
                cls._append_if_present(blocks, "Study", study.get("title"))
                for claim in item.claims:
                    wording = claim.snapshot.get("wording") or claim.snapshot.get("claim_id")
                    blocks.append(
                        _DocumentBlock(
                            "bullet",
                            f"Claim {claim.object_uuid} v{claim.object_version}: "
                            f"{wording or ''}",
                        )
                    )

        blocks.append(_DocumentBlock("h1", "Content Provenance"))
        if not draft.content_blocks:
            blocks.append(_DocumentBlock("body", "No frozen narrative content blocks."))
        for content in draft.content_blocks:
            blocks.append(_DocumentBlock("h2", content.block_id))
            blocks.append(
                _DocumentBlock(
                    "body",
                    f"Origin: {content.origin}; review status: {content.review_status}",
                )
            )
            if content.model_id:
                blocks.append(_DocumentBlock("body", f"Model: {content.model_id}"))
            blocks.append(_DocumentBlock("body", content.text))
            for reference in content.source_refs:
                blocks.append(
                    _DocumentBlock(
                        "bullet",
                        f"Source: {reference.object_uuid} v{reference.object_version}",
                    )
                )
            if content.content_ref is not None:
                blocks.append(
                    _DocumentBlock(
                        "bullet",
                        "Frozen content: "
                        f"{content.content_ref.object_uuid} "
                        f"v{content.content_ref.object_version}",
                    )
                )

        blocks.append(_DocumentBlock("h1", "Completeness Report"))
        if draft.completeness_report is None:
            blocks.append(
                _DocumentBlock("body", "No frozen report-level completeness snapshot.")
            )
        else:
            gap_report = draft.completeness_report.gap_report
            blocks.extend(
                [
                    _DocumentBlock(
                        "body",
                        "Snapshot: "
                        f"{draft.completeness_report.snapshot_ref.object_uuid} "
                        f"v{draft.completeness_report.snapshot_ref.object_version}",
                    ),
                    _DocumentBlock(
                        "body",
                        f"Complete: {'yes' if gap_report.complete else 'no'}; "
                        f"claims={gap_report.performance_claim_count}; "
                        f"gaps={gap_report.gap_claim_count}",
                    ),
                ]
            )
            for claim in gap_report.claims:
                blocks.append(
                    _DocumentBlock(
                        "h3",
                        f"Claim {claim.claim.object_uuid} v{claim.claim.object_version}",
                    )
                )
                blocks.append(_DocumentBlock("body", claim.wording))
                if not claim.findings:
                    blocks.append(_DocumentBlock("bullet", "No evidence gaps."))
                for finding in claim.findings:
                    suffix = ""
                    if finding.evidence is not None:
                        suffix = (
                            f" [{finding.evidence.object_uuid} "
                            f"v{finding.evidence.object_version}]"
                        )
                    blocks.append(
                        _DocumentBlock(
                            "bullet",
                            f"{finding.rule_code}: {finding.message}{suffix}",
                        )
                    )

        blocks.append(_DocumentBlock("h1", "Traceability Appendix"))
        for entry in draft.traceability_appendix:
            blocks.append(
                _DocumentBlock(
                    "h3",
                    f"{entry.section_type}: "
                    f"{entry.performance_result.object_uuid} "
                    f"v{entry.performance_result.object_version}",
                )
            )
            blocks.append(
                _DocumentBlock(
                    "bullet",
                    f"Study: {entry.study.object_uuid} v{entry.study.object_version}",
                )
            )
            for claim in entry.claims:
                blocks.append(
                    _DocumentBlock(
                        "bullet",
                        f"Claim: {claim.object_uuid} v{claim.object_version}",
                    )
                )
            for source in entry.statistical_sources:
                blocks.append(
                    _DocumentBlock(
                        "bullet",
                        f"Statistical source: {source.object_uuid} v{source.object_version}",
                    )
                )
        return blocks

    @staticmethod
    def _append_if_present(
        blocks: list[_DocumentBlock],
        label: str,
        value,
    ) -> None:
        if value is not None and str(value).strip():
            blocks.append(_DocumentBlock("body", f"{label}: {value}"))

    @staticmethod
    def _render_html(
        draft: PERDraftPayload,
        blocks: list[_DocumentBlock],
    ) -> bytes:
        tags = {
            "title": "h1",
            "h1": "h2",
            "h2": "h3",
            "h3": "h4",
            "body": "p",
            "bullet": "p",
        }
        body_parts = []
        for block in blocks:
            tag = tags[block.style]
            css_class = f' class="{block.style}"'
            body_parts.append(
                f"<{tag}{css_class}>{html.escape(block.text)}</{tag}>"
            )
        document = (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            "<title>Performance Evaluation Report</title>"
            "<style>body{font-family:Arial,sans-serif;max-width:980px;margin:40px auto;"
            "line-height:1.45}h1,h2,h3,h4{page-break-after:avoid}.bullet{margin-left:2em}"
            ".body{white-space:pre-wrap}</style></head><body>"
            f"<div data-per-schema=\"{html.escape(draft.schema_version)}\">"
            + "".join(body_parts)
            + "</div></body></html>"
        )
        return document.encode("utf-8")

    @classmethod
    def _render_docx(cls, blocks: list[_DocumentBlock]) -> bytes:
        paragraphs = []
        sizes = {"title": 36, "h1": 30, "h2": 26, "h3": 22, "body": 20, "bullet": 20}
        for block in blocks:
            text = f"• {block.text}" if block.style == "bullet" else block.text
            bold = block.style in {"title", "h1", "h2", "h3"}
            properties = [f'<w:sz w:val="{sizes[block.style]}"/>']
            if bold:
                properties.append("<w:b/>")
            paragraphs.append(
                "<w:p><w:r><w:rPr>"
                + "".join(properties)
                + "</w:rPr><w:t xml:space=\"preserve\">"
                + xml_escape(text)
                + "</w:t></w:r></w:p>"
            )
        document_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body>"
            + "".join(paragraphs)
            + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>'
            "</w:sectPr></w:body></w:document>"
        ).encode("utf-8")
        content_types = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>"
        ).encode("utf-8")
        root_rels = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/>'
            "</Relationships>"
        ).encode("utf-8")
        document_rels = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
        ).encode("utf-8")

        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
            cls._write_zip_entry(archive, "[Content_Types].xml", content_types)
            cls._write_zip_entry(archive, "_rels/.rels", root_rels)
            cls._write_zip_entry(archive, "word/document.xml", document_xml)
            cls._write_zip_entry(
                archive,
                "word/_rels/document.xml.rels",
                document_rels,
            )
        return stream.getvalue()

    @staticmethod
    def _write_zip_entry(
        archive: zipfile.ZipFile,
        path: str,
        content: bytes,
    ) -> None:
        info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        info.external_attr = 0o600 << 16
        archive.writestr(info, content)

    @classmethod
    def _render_pdf(cls, blocks: list[_DocumentBlock]) -> bytes:
        lines: list[tuple[str, int, int]] = []
        sizes = {"title": 16, "h1": 14, "h2": 12, "h3": 11, "body": 10, "bullet": 10}
        leading = {"title": 24, "h1": 21, "h2": 18, "h3": 16, "body": 14, "bullet": 14}
        widths = {"title": 58, "h1": 68, "h2": 78, "h3": 86, "body": 95, "bullet": 92}

        for block in blocks:
            prefix = "- " if block.style == "bullet" else ""
            raw_lines = block.text.splitlines() or [""]
            first = True
            for raw_line in raw_lines:
                wrapped = textwrap.wrap(
                    raw_line,
                    width=widths[block.style],
                    replace_whitespace=False,
                    drop_whitespace=True,
                ) or [""]
                for wrapped_line in wrapped:
                    text = (prefix if first else "  " if prefix else "") + wrapped_line
                    cls._encode_pdf_text(text)
                    lines.append((text, sizes[block.style], leading[block.style]))
                    first = False

        pages: list[list[tuple[str, int, int]]] = []
        current: list[tuple[str, int, int]] = []
        y = 790
        for line in lines:
            if y - line[2] < 48 and current:
                pages.append(current)
                current = []
                y = 790
            current.append(line)
            y -= line[2]
        if current or not pages:
            pages.append(current)

        return cls._build_pdf(pages)

    @staticmethod
    def _encode_pdf_text(text: str) -> bytes:
        try:
            return text.encode("cp1252")
        except UnicodeEncodeError as exc:
            raise BaselineValidationError(
                "PDF renderer supports WinAnsi text only; use HTML or DOCX for "
                "characters outside Windows-1252"
            ) from exc

    @classmethod
    def _build_pdf(cls, pages: list[list[tuple[str, int, int]]]) -> bytes:
        objects: dict[int, bytes] = {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        }
        page_ids = []
        next_id = 4
        for page in pages:
            page_id = next_id
            content_id = next_id + 1
            next_id += 2
            page_ids.append(page_id)
            content = cls._pdf_page_stream(page)
            objects[page_id] = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode("ascii")
            objects[content_id] = (
                f"<< /Length {len(content)} >>\nstream\n".encode("ascii")
                + content
                + b"\nendstream"
            )
        kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
        objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode(
            "ascii"
        )

        header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
        output = bytearray(header)
        offsets = {0: 0}
        for object_id in range(1, max(objects) + 1):
            offsets[object_id] = len(output)
            output.extend(f"{object_id} 0 obj\n".encode("ascii"))
            output.extend(objects[object_id])
            output.extend(b"\nendobj\n")
        xref_offset = len(output)
        object_count = max(objects) + 1
        output.extend(f"xref\n0 {object_count}\n".encode("ascii"))
        output.extend(b"0000000000 65535 f \n")
        for object_id in range(1, object_count):
            output.extend(f"{offsets[object_id]:010d} 00000 n \n".encode("ascii"))
        output.extend(
            (
                f"trailer\n<< /Size {object_count} /Root 1 0 R >>\n"
                f"startxref\n{xref_offset}\n%%EOF\n"
            ).encode("ascii")
        )
        return bytes(output)

    @classmethod
    def _pdf_page_stream(cls, page: list[tuple[str, int, int]]) -> bytes:
        commands = [b"BT", b"50 790 Td"]
        first = True
        for text, size, leading in page:
            if not first:
                commands.append(f"0 -{leading} Td".encode("ascii"))
            commands.append(f"/F1 {size} Tf".encode("ascii"))
            encoded = cls._encode_pdf_text(text)
            escaped = (
                encoded.replace(b"\\", b"\\\\")
                .replace(b"(", b"\\(")
                .replace(b")", b"\\)")
            )
            commands.append(b"(" + escaped + b") Tj")
            first = False
        commands.append(b"ET")
        return b"\n".join(commands)
