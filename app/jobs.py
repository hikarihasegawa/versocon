"""Job in background per operazioni lunghe: progresso reale e annullamento.

L'app è locale e a utente singolo: lo stato dei job vive in memoria e i file
di lavoro nella cartella di sessione (cancellata alla chiusura). Ogni job gira
in un thread dedicato, così la richiesta HTTP di avvio ritorna subito e la UI
può interrogare lo stato e annullare. L'annullamento è cooperativo: i worker
controllano ``job.cancelled`` nei punti sicuri e i processi esterni (ffmpeg)
vengono terminati.
"""
from __future__ import annotations

import shutil
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from converters.report import OperationCancelled

TERMINAL = frozenset({"done", "error", "cancelled"})


class JobError(Exception):
    """Errore mostrabile all'utente: messaggio già tradotto dal worker."""

    def __init__(self, message: str, result: dict | None = None):
        super().__init__(message)
        self.result = result


class Job:
    """Un'operazione lunga con stato, avanzamento e richiesta di annullo."""

    def __init__(self, job_id: str, op: str, lang: str, work_dir: Path,
                 total: int | None = None, unit: str | None = None):
        self.id = job_id
        self.op = op
        self.lang = lang
        self.work_dir = work_dir
        self.status = "queued"          # queued | running | done | error | cancelled
        self.done: int | None = None
        self.total = total
        self.unit = unit                # "file" | "page" | "second" | None
        self.message_key: str | None = None
        self.message_params: dict[str, object] = {}
        self.result: dict | None = None
        self.error: str | None = None
        self.created = time.time()
        self.updated = self.created
        self.thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()

    @property
    def cancelled(self) -> bool:
        """True quando l'utente ha chiesto l'annullamento (callback per i converter)."""
        return self._cancel.is_set()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set() and self.status not in TERMINAL

    def request_cancel(self) -> bool:
        """Segnala l'annullo; False se il job è già terminato."""
        if self.status in TERMINAL:
            return False
        self._cancel.set()
        self.updated = time.time()
        return True

    def progress(self, done: int | None = None, total: int | None = None,
                 key: str | None = None, unit: str | None = None, **params: object) -> None:
        """Aggiorna l'avanzamento (thread-safe)."""
        with self._lock:
            self.updated = time.time()
            if total is not None:
                self.total = total
            if done is not None:
                self.done = done
            if unit is not None:
                self.unit = unit
            if key is not None:
                self.message_key = key
                self.message_params = dict(params)

    def snapshot(self) -> dict:
        """Copia coerente dello stato per la risposta API."""
        with self._lock:
            return {
                "id": self.id,
                "op": self.op,
                "status": self.status,
                "done": self.done,
                "total": self.total,
                "unit": self.unit,
                "message_key": self.message_key,
                "message_params": dict(self.message_params),
                "result": self.result,
                "error": self.error,
                "cancel_requested": self.cancel_requested,
            }


class JobManager:
    """Registro in memoria dei job con pulizia dei più vecchi (TTL)."""

    def __init__(self, root: Path, ttl_s: float = 900.0):
        self.root = root
        self.ttl_s = ttl_s
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, op: str, lang: str, total: int | None = None,
               unit: str | None = None) -> Job:
        """Registra un job e crea la sua cartella di lavoro."""
        self.sweep()
        job_id = uuid.uuid4().hex[:12]
        work_dir = self.root / job_id
        work_dir.mkdir(parents=True, exist_ok=True)
        job = Job(job_id, op, lang, work_dir, total=total, unit=unit)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        """Job per id, None se sconosciuto o scaduto."""
        self.sweep()
        with self._lock:
            return self._jobs.get(job_id)

    def discard(self, job: Job) -> None:
        """Elimina un job mai avviato (es. upload rifiutato) e i suoi file."""
        with self._lock:
            self._jobs.pop(job.id, None)
        shutil.rmtree(job.work_dir, ignore_errors=True)

    def start(self, job: Job, worker: Callable[[Job], dict | None]) -> Job:
        """Avvia il worker in un thread daemon; ``worker`` ritorna il risultato.

        Lo stato terminale è pubblicato DOPO la pulizia della cartella di
        lavoro: chi vede ``done``/``error``/``cancelled`` ha già i file liberi.
        """
        def runner() -> None:
            job.status = "running"
            job.updated = time.time()
            status, error, result, error_result = "done", None, None, None
            try:
                result = worker(job)
            except OperationCancelled:
                status = "cancelled"
            except JobError as e:
                status, error, error_result = "error", str(e), e.result
            except Exception as e:  # noqa: BLE001 - errore inatteso: riportato alla UI
                status, error = "error", str(e)
            finally:
                shutil.rmtree(job.work_dir, ignore_errors=True)
                job.result = error_result if error_result is not None else result
                job.error = error
                job.status = status
                job.updated = time.time()

        job.thread = threading.Thread(target=runner, name=f"versocon-job-{job.id}", daemon=True)
        job.thread.start()
        return job

    def sweep(self) -> None:
        """Rimuove i job terminati entro il TTL (i file sono già stati cancellati)."""
        cutoff = time.time() - self.ttl_s
        with self._lock:
            expired = [jid for jid, j in self._jobs.items()
                       if j.status in TERMINAL and j.updated < cutoff]
            for jid in expired:
                self._jobs.pop(jid, None)
