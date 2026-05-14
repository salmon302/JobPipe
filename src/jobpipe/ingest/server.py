# Purpose: Provide a local HTTP ingest server for browser extension payloads.
# Author: Seth Nenninger (GPT-5.2-Codex Agent)
# Timestamp: 2026-05-12T00:00:00Z
# Changelog: Add threaded ingest server with JSON request handling.

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import threading
from typing import Any

from jobpipe.config import Settings
from jobpipe.ingest.service import IngestPayloadError, IngestResult, JobIngestService
from jobpipe.pipeline import MissingMasterCVError, RunAlreadyInProgressError

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestServerConfig:
    host: str
    port: int
    max_payload_bytes: int


class IngestHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        service: JobIngestService,
        config: IngestServerConfig,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.service = service
        self.config = config


class IngestRequestHandler(BaseHTTPRequestHandler):
    server: IngestHTTPServer

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        LOGGER.info("IngestServer | %s", format % args)

    def _add_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._add_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        if content_length <= 0:
            raise IngestPayloadError("Request body is required")

        if content_length > self.server.config.max_payload_bytes:
            raise IngestPayloadError("Request payload exceeds allowed size")

        raw = self.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise IngestPayloadError("Invalid JSON payload") from exc

        if not isinstance(payload, dict):
            raise IngestPayloadError("Payload must be a JSON object")

        return payload

    def _path(self) -> str:
        return self.path.split("?", 1)[0]

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._add_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self._path() != "/health":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not-found"})
            return

        self._send_json(
            HTTPStatus.OK,
            {
                "status": "ok",
                "db_path": str(self.server.service.settings.db_path),
                "job_description_path": str(
                    self.server.service.settings.job_description_path
                ),
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        if self._path() != "/ingest":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not-found"})
            return

        try:
            payload = self._read_json_body()
            LOGGER.info("IngestServer | Received ingest request with %d top-level keys", len(payload))
            if "jobs" in payload:
                LOGGER.info("IngestServer | Batch has %d jobs", len(payload["jobs"]))
            result = self.server.service.ingest_payload(payload)
        except IngestPayloadError as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid-payload", "message": str(exc)},
            )
            return
        except MissingMasterCVError as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": "missing-master-cv", "message": str(exc)},
            )
            return
        except RunAlreadyInProgressError as exc:
            self._send_json(
                HTTPStatus.CONFLICT,
                {"error": "run-in-progress", "message": str(exc)},
            )
            return
        except Exception as exc:  # pragma: no cover - defensive error handling
            LOGGER.exception("Ingest handler failed")
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "server-error", "message": str(exc)},
            )
            return

        self._send_json(HTTPStatus.OK, _result_payload(result))

    def do_GET(self) -> None:  # noqa: N802
        path = self._path()
        if path == "/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "db_path": str(self.server.service.settings.db_path),
                    "job_description_path": str(
                        self.server.service.settings.job_description_path
                    ),
                },
            )
            return

        # Status endpoint: /ingest/status/{run_id}
        if path.startswith("/ingest/status/"):
            run_id = path.split("/ingest/status/")[1].split("?")[0]
            try:
                status = self.server.service.get_run_status(run_id)
                self._send_json(HTTPStatus.OK, status)
            except ValueError as exc:
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    {"error": "run-not-found", "message": str(exc)},
                )
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not-found"})


def _result_payload(result: IngestResult) -> dict[str, Any]:
    payload = {
        "run_id": result.run_id,
        "ingested": result.ingested,
        "inserted": result.inserted,
        "updated": result.updated,
        "scored": result.scored,
        "above_threshold": result.above_threshold,
        "notified": result.notified,
    }
    
    # Add early-queue status indicators
    if result.scoring_in_progress:
        payload["status"] = "queued"
        payload["message"] = "Jobs added to queue. You can continue browsing!"
        payload["scoring_in_progress"] = True
    else:
        payload["status"] = "completed"
        payload["scoring_in_progress"] = False
    
    return payload


class IngestServer:
    def __init__(self, config: IngestServerConfig, service: JobIngestService) -> None:
        self._config = config
        self._service = service
        self._server: IngestHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def config(self) -> IngestServerConfig:
        return self._config

    def endpoint(self) -> str:
        return f"http://{self._config.host}:{self._config.port}"

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self._server is not None:
            return

        server = IngestHTTPServer(
            (self._config.host, self._config.port),
            IngestRequestHandler,
            service=self._service,
            config=self._config,
        )
        thread = threading.Thread(
            target=server.serve_forever,
            name="JobPipeIngestServer",
            daemon=True,
        )
        thread.start()

        self._server = server
        self._thread = thread
        LOGGER.info("Ingest server started at %s", self.endpoint())

    def stop(self) -> None:
        if self._server is None:
            return

        self._server.shutdown()
        self._server.server_close()
        self._server = None

        if self._thread is not None:
            self._thread.join(timeout=2)
        self._thread = None
        LOGGER.info("Ingest server stopped")

    def serve_forever(self) -> None:
        if self._server is None:
            self._server = IngestHTTPServer(
                (self._config.host, self._config.port),
                IngestRequestHandler,
                service=self._service,
                config=self._config,
            )

        LOGGER.info("Ingest server running at %s", self.endpoint())
        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            LOGGER.info("Ingest server interrupted")
        finally:
            self.stop()

def run_ingest_server(
    settings: Settings,
    host: str | None = None,
    port: int | None = None,
) -> None:
    config = IngestServerConfig(
        host=host or settings.ingest_host,
        port=port or settings.ingest_port,
        max_payload_bytes=settings.ingest_max_payload_bytes,
    )
    server = IngestServer(config=config, service=JobIngestService(settings))
    server.serve_forever()
