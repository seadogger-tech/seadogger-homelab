import tempfile
import unittest
from pathlib import Path

from preflight import stage


class PayloadStagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / "source"
        self.payload = root / "payload"
        self.source.mkdir()

    def write(self, name, content="sample"):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def test_stages_only_pages_and_rendered_images(self):
        self.write("Home.md")
        self.write("memory_bank/Index.md")
        self.write("images/logo.png")
        self.write("images/Logo.key")
        self.write("tools/build_all.py")
        self.write(".DS_Store")
        self.assertEqual(stage(self.source, self.payload), 3)
        self.assertEqual(
            sorted(str(path.relative_to(self.payload)) for path in self.payload.rglob("*") if path.is_file()),
            ["Home.md", "images/logo.png", "memory_bank/Index.md"],
        )

    def test_rejects_unexpected_files_before_creating_payload(self):
        self.write("images/private.json")
        with self.assertRaisesRegex(ValueError, "Unexpected wiki source file"):
            stage(self.source, self.payload)
        self.assertFalse(self.payload.exists())

    def test_rejects_symlinks_in_published_paths(self):
        self.write("Home.md")
        (self.source / "Other.md").symlink_to(self.source / "Home.md")
        with self.assertRaisesRegex(ValueError, "symlink"):
            stage(self.source, self.payload)


if __name__ == "__main__":
    unittest.main()
