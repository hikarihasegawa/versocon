"""Progresso e annullamento per operazioni lunghe (interfaccia dei converter).

I converter non conoscono i job: ricevono due callback opzionali.

``progress(done, total, phase)``
    Unità completate su ``total`` (None se il totale non è noto); ``phase`` è
    la fase in corso nel vocabolario del converter (``files``, ``pages``,
    ``seconds``) e serve al chiamante per etichettare l'avanzamento.

``cancel()``
    Restituisce True se l'operazione è stata annullata; i converter la
    controllano nei punti sicuri e sollevano ``OperationCancelled``.
"""
from __future__ import annotations

from collections.abc import Callable

ProgressFn = Callable[[int | None, int | None, str | None], None]
CancelFn = Callable[[], bool]


class OperationCancelled(Exception):
    """L'operazione è stata annullata su richiesta (cooperativo)."""


def report(
    progress: ProgressFn | None,
    done: int | None = None,
    total: int | None = None,
    phase: str | None = None,
) -> None:
    """Invia un aggiornamento di avanzamento, se il chiamante lo richiede."""
    if progress is not None:
        progress(done, total, phase)


def check_cancelled(cancel: CancelFn | None) -> None:
    """Solleva ``OperationCancelled`` quando la callback segnala annullamento."""
    if cancel is not None and cancel():
        raise OperationCancelled()
