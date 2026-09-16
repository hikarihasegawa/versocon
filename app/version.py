"""Versione dell'applicazione: unica fonte di verità.

I workflow `release.yml` e `msix.yml` riscrivono questo file dal tag (o
dall'input manuale) prima della build, così UI, `/api/config` e installer non
possono divergere.
"""
__version__ = "0.3.1"
