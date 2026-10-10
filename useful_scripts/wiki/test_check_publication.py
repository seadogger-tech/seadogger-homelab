import tempfile
import unittest
from pathlib import Path

from check_publication import check, digest


class PublicationChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / "source"
        self.published = root / "published"
        self.source.mkdir()
        self.published.mkdir()

    def write(self, directory, text, name="Page.md"):
        (directory / name).write_text(text)

    def errors(self, exceptions=None):
        return check(self.source, self.published, exceptions or {})

    def test_blocks_large_page_truncation_and_unclosed_fence(self):
        self.write(self.published, "# Recovery\n" + "step\n" * 120 + "```mermaid\ngraph TD\n```\n")
        self.write(self.source, "# Recovery\n```mermaid\ngraph TD\n")
        errors = self.errors()
        self.assertTrue(any("large reduction" in error for error in errors))
        self.assertTrue(any("unclosed Markdown fence" in error for error in errors))

    def test_exact_hash_exception_allows_intentional_reduction(self):
        previous = "old\n" * 120
        current = "# Short replacement\n"
        self.write(self.published, previous)
        self.write(self.source, current)
        exceptions = {
            "Page.md": {
                "published_sha256": digest(previous),
                "source_sha256": digest(current),
                "reason": "Reviewed replacement of historical notes",
            }
        }
        self.assertEqual(self.errors(exceptions), [])
        exceptions["Page.md"]["source_sha256"] = "outdated"
        self.assertTrue(any("large reduction" in error for error in self.errors(exceptions)))

    def test_large_page_deletion_requires_exact_hash_exception(self):
        previous = "obsolete section\n" * 100
        self.write(self.published, previous)
        self.assertTrue(any("large reduction" in error for error in self.errors()))
        exceptions = {
            "Page.md": {
                "published_sha256": digest(previous),
                "source_sha256": None,
                "reason": "Reviewed retirement of this page",
            }
        }
        self.assertEqual(self.errors(exceptions), [])

    def test_blocks_personal_paths_account_buckets_and_dated_receipts(self):
        self.write(
            self.source,
            "# Runbook\n"
            "cd /Users/alice/example-project\n"
            "s3://example-backup-123456789012/data/\n"
            "## Staging evidence: 2020-01-02 UTC\n"
            "| Check | Observed result |\n",
        )
        errors = self.errors()
        self.assertEqual(len(errors), 4)

    def test_existing_public_text_does_not_block_unchanged_publication(self):
        text = "# Existing page\n/Users/alice/example-project\n"
        self.write(self.published, text)
        self.write(self.source, text)
        self.assertEqual(self.errors(), [])

    def test_clean_new_page_passes(self):
        self.write(self.source, "# Procedure\n```bash\ncd /ABSOLUTE/CORE\n```\n")
        self.assertEqual(self.errors(), [])


if __name__ == "__main__":
    unittest.main()
