"""
Sandbox — DEPRECATED
=====================

This module is no longer the canonical execution layer.

MIGRATION: Use executor.py (Executor class) instead.

What changed:
    Old: Sandbox(handlers).execute(ir)  — handlers lived in-process
    New: Executor().execute(ir)         — dispatches to worker.py subprocess

The Executor has the same .execute(ir) → TaintedValue interface as Sandbox,
so call sites are unchanged. Runtime.sandbox now returns an Executor instance.

Why deprecated:
    Sandbox held callable handler functions inside the main process.
    A determined caller with access to the Python runtime could reach those
    functions via the Sandbox instance or through Python introspection.
    The new Executor holds no handlers — it holds only a path to worker.py.
    Handlers now live exclusively in the worker subprocess.

This file is kept to avoid import errors in any code that imports Sandbox
directly, but it is not the canonical path. It will be removed in a future
cleanup pass.
"""

# Re-export Executor under the Sandbox name for any direct importers.
# Runtime no longer uses this file.
from executor import Executor as Sandbox  # noqa: F401

__all__ = ["Sandbox"]
