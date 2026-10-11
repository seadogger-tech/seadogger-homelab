"""Patch Hermes Signal sends to use the signal-cli data URI attachment API."""

import sys
from pathlib import Path


OLD_SEND = '''    async def _send_file(self, chat_id: str, file_path: str, caption: Optional[str], fail_error: str) -> SendResult:
        """Send one local file as a Signal attachment via the ``send`` RPC."""
        params = await self._with_target(
            {"account": self.account, "message": caption or "", "attachments": [file_path]}, chat_id)
        _, err = await self._rpc_send(params, fail_error)
        return err or SendResult(success=True)
'''

NEW_SEND = '''    async def _attachment_data_uri(self, file_path: str) -> str:
        """Encode one local file for a signal-cli daemon in another pod."""
        path = Path(file_path)
        raw = await asyncio.to_thread(path.read_bytes)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return (
            f"data:{mime};filename={quote(path.name, safe='')};base64,"
            f"{base64.b64encode(raw).decode('ascii')}")

    async def _send_file(self, chat_id: str, file_path: str, caption: Optional[str], fail_error: str) -> SendResult:
        """Send file bytes because signal-cli runs in a different pod."""
        try:
            attachment = await self._attachment_data_uri(file_path)
        except OSError as exc:
            return SendResult(success=False, error=f"Attachment read failed: {exc}")
        params = await self._with_target(
            {"account": self.account, "message": caption or "", "attachments": [attachment]}, chat_id)
        _, err = await self._rpc_send(params, fail_error)
        return err or SendResult(success=True)
'''

OLD_BATCH = '''        send_timeout, max_attempts = _signal_send_timeout(n), SIGNAL_RATE_LIMIT_MAX_ATTEMPTS
        for attempt in range(1, max_attempts + 1):
'''

NEW_BATCH = '''        send_timeout, max_attempts = _signal_send_timeout(n), SIGNAL_RATE_LIMIT_MAX_ATTEMPTS
        try:
            params = dict(params, attachments=[
                await self._attachment_data_uri(path) for path in params["attachments"]])
        except OSError as exc:
            logger.warning("Signal: failed to read batch attachment: %s", exc)
            return False
        for attempt in range(1, max_attempts + 1):
'''

OLD_CHUNKS = '''        per = SIGNAL_MAX_ATTACHMENTS_PER_MSG
        att_batches = [attachments[i:i + per] for i in range(0, len(attachments), per)]
'''

NEW_CHUNKS = '''        per = SIGNAL_MAX_ATTACHMENTS_PER_MSG
        # Base64 expands file bytes by one third. Keep each JSON request below
        # the proxy's 140 MiB limit even when several images are selected.
        att_batches = []
        batch = []
        batch_bytes = 0
        for path in attachments:
            try:
                file_bytes = Path(path).stat().st_size
            except OSError as exc:
                logger.warning("Signal: batch attachment disappeared before send: %s", exc)
                continue
            if batch and (len(batch) >= per or batch_bytes + file_bytes > SIGNAL_MAX_ATTACHMENT_SIZE):
                att_batches.append(batch)
                batch, batch_bytes = [], 0
            batch.append(path)
            batch_bytes += file_bytes
        if batch:
            att_batches.append(batch)
'''

OLD_STANDALONE_BATCHES = '''        per_batch = rl.SIGNAL_MAX_ATTACHMENTS_PER_MSG
        att_batches = [attachment_paths[i:i + per_batch] for i in range(0, len(attachment_paths), per_batch)] or [[]]
'''

NEW_STANDALONE_BATCHES = '''        per_batch = rl.SIGNAL_MAX_ATTACHMENTS_PER_MSG
        max_batch_bytes = 100 * 1024 * 1024  # match Signal adapter and 140 MiB proxy limit
        att_batches = []
        batch, batch_bytes = [], 0
        for path in attachment_paths:
            try:
                file_bytes = Path(path).stat().st_size
            except OSError as exc:
                logger.warning("Signal media file disappeared before send: %s", exc)
                continue
            if batch and (len(batch) >= per_batch or batch_bytes + file_bytes > max_batch_bytes):
                att_batches.append(batch)
                batch, batch_bytes = [], 0
            batch.append(path)
            batch_bytes += file_bytes
        if batch:
            att_batches.append(batch)
        att_batches = att_batches or [[]]
'''

OLD_STANDALONE_POST = '''        async def _post(batch_attachments, batch_message):
            resp = await _rpc_send(batch_message, id_prefix="send", attachments=batch_attachments, styled=True,
                                   timeout=rl._signal_send_timeout(len(batch_attachments)))
'''

NEW_STANDALONE_POST = '''        async def _post(batch_attachments, batch_message):
            encoded = []
            for path in batch_attachments:
                raw = await asyncio.to_thread(Path(path).read_bytes)
                mime = mimetypes.guess_type(Path(path).name)[0] or "application/octet-stream"
                encoded.append(
                    f"data:{mime};filename={quote(Path(path).name, safe='')};base64,"
                    f"{base64.b64encode(raw).decode('ascii')}")
            resp = await _rpc_send(batch_message, id_prefix="send", attachments=encoded, styled=True,
                                   timeout=rl._signal_send_timeout(len(batch_attachments)))
'''


def main(path: Path) -> None:
    source = path.read_text()
    if (source.count(OLD_SEND) != 1 or source.count(OLD_BATCH) != 1
            or source.count(OLD_CHUNKS) != 1
            or source.count("import logging\n") != 1 or "import mimetypes\n" in source):
        raise SystemExit("Hermes Signal adapter changed; review the attachment patch before building")
    source = source.replace("import logging\n", "import logging\nimport mimetypes\n", 1)
    source = source.replace(OLD_SEND, NEW_SEND, 1)
    source = source.replace(OLD_BATCH, NEW_BATCH, 1)
    path.write_text(source.replace(OLD_CHUNKS, NEW_CHUNKS, 1))


def patch_standalone_sender(path: Path) -> None:
    source = path.read_text()
    if (source.count(OLD_STANDALONE_BATCHES) != 1 or source.count(OLD_STANDALONE_POST) != 1
            or source.count("import asyncio\n") != 1 or "import mimetypes\n" in source):
        raise SystemExit("Hermes standalone Signal sender changed; review the attachment patch before building")
    source = source.replace("import asyncio\n", "import asyncio\nimport base64\nimport mimetypes\n", 1)
    source = source.replace("import os\n", "import os\nfrom pathlib import Path\nfrom urllib.parse import quote\n", 1)
    source = source.replace(OLD_STANDALONE_BATCHES, NEW_STANDALONE_BATCHES, 1)
    path.write_text(source.replace(OLD_STANDALONE_POST, NEW_STANDALONE_POST, 1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
    patch_standalone_sender(Path(sys.argv[2]))
