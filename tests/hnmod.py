"""Shared loader for the single-file `hn` script under test.

`hn` has no .py extension, so it cannot be imported normally. Each test
module loads it through this helper to avoid duplicating the boilerplate.
"""

import importlib.machinery
import importlib.util
from pathlib import Path

HN_PATH = Path(__file__).resolve().parents[1] / "hn"


def load_hn_module(name="hn_under_test"):
    loader = importlib.machinery.SourceFileLoader(name, str(HN_PATH))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module
