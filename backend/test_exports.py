"""Regression checks for downloadable report structure and content."""
import io
import unittest
import zipfile
import xml.etree.ElementTree as ET

from exports import export_report, _chunk_pdf_pages, _markdown_blocks


class ExportTests(unittest.TestCase):
    def test_word_preserves_unicode_and_formats_tables(self):
        report = "# Findings\nCaf\u00e9 \u65e5\u672c\u8a9e\n**Important** [source](https://example.org)\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n1. First\n2. Second"
        data, mime, extension = export_report(report, "docx")
        self.assertEqual(extension, "docx")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name in archive.namelist():
                ET.fromstring(archive.read(name))
            document = ET.fromstring(archive.read("word/document.xml"))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            text = "".join(document.itertext())
            self.assertIn("\u65e5\u672c\u8a9e", text)
            self.assertIn("Caf\u00e9", text)
            self.assertIn("https://example.org", text)
            self.assertIn("1. First", text)
            self.assertEqual(len(document.findall(".//w:tbl", ns)), 1)
            self.assertTrue(document.findall(".//w:b", ns))
            self.assertIn("word/header.xml", archive.namelist())
            self.assertIn("word/footer.xml", archive.namelist())

    def test_pdf_pages_keep_long_content(self):
        report = "# Report\n" + ("evidence " * 4000) + "\nFINAL_SENTINEL"
        pages = _chunk_pdf_pages(_markdown_blocks(report))
        self.assertGreater(len(pages), 2)
        costs = {"title": 30, "h2": 24, "h3": 19, "space": 8}
        for page in pages:
            self.assertLessEqual(sum(costs.get(kind, 15) for kind, _ in page), 610)
        self.assertIn("FINAL_SENTINEL", " ".join(text for page in pages for _, text in page))
        data, mime, extension = export_report(report, "pdf")
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertIn(b"FINAL_SENTINEL", data)

    def test_markdown_is_unchanged(self):
        report = "# Test\n\n\u65e5\u672c\u8a9e **bold**\n"
        self.assertEqual(export_report(report, "md")[0].decode("utf-8"), report)

    def test_unsupported_format(self):
        with self.assertRaises(ValueError):
            export_report("Report", "exe")


if __name__ == "__main__":
    unittest.main()
