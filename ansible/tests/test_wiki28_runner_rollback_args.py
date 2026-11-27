"""Regression checks for Wiki 28's single-play rollback runner arguments."""
import json
import re
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parents[2]
WIKI = CORE / "docs/wiki/28-Ansible-Runner.md"
WIKI_05 = CORE / "docs/wiki/05-GitOps-and-IaC.md"
PLAY_ARGUMENTS = (
    ("nextcloud-db (`nextcloud_postgresql`)", "<PRIOR_DB_PIN>"),
    ("nextcloud-redis (`nextcloud_redis`)", "<PRIOR_REDIS_PIN>"),
    ("s3-backup (`nextcloud_s3_backup_deploy.yml`)", None),
    ("xmltv-proxy (`jellyfin_xmltv_proxy_deploy.yml`)", None),
)


def wiki05_arguments():
    text = WIKI_05.read_text()
    section = text.split("##### Runner Job arguments for the four plays", 1)[1]
    section = section.split("\n##### ", 1)[0]
    arguments = []
    for heading, pin_placeholder in PLAY_ARGUMENTS:
        play_section = section.split(f"**{heading}**", 1)[1].split("```", 2)[1]
        encoded = re.search(r"-e '({[^\n]+})'", play_section).group(1)
        extra_vars = json.loads(encoded)
        if pin_placeholder:
            revision_key = next(key for key in extra_vars if key.endswith("_revision"))
            extra_vars[revision_key] = pin_placeholder
        arguments.append(extra_vars)
    return arguments


class TestWiki28RunnerRollbackArgs(unittest.TestCase):
    def test_each_remaining_play_has_only_its_own_flag_enabled(self):
        text = WIKI.read_text()
        commands = text.split("After the raw-blob check, run each remaining play separately:", 1)[1]
        command_block = commands.split("```", 2)[1]
        entries = re.findall(
            r"ansible-playbook[^\n]*\\\n\s+-e '(\{[^\n]+\})'",
            command_block,
        )
        self.assertEqual(len(entries), 4, "step 4 must document all four remaining plays")

        expected = wiki05_arguments()
        for (play, pin_placeholder), encoded, expected_args in zip(PLAY_ARGUMENTS, entries, expected):
            with self.subTest(play=play):
                extra_vars = json.loads(encoded)
                self.assertEqual(extra_vars, expected_args)
                if pin_placeholder:
                    revision_key = next(key for key in extra_vars if key.endswith("_revision"))
                    sample = extra_vars[revision_key].replace(pin_placeholder, "a" * 40)
                    self.assertRegex(sample, r"^[0-9a-f]{40}$")

        self.assertIn(
            "before rollout in the prior-state record (wiki 05, *Rollback* column)",
            text,
        )


if __name__ == "__main__":
    unittest.main()
