"""Run offline cloud checks with temporary files inside the ignored workspace."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


def main():
    scratch = ROOT/'runs/local_check_tmp'
    scratch.mkdir(parents=True, exist_ok=True)
    os.environ['TMP'] = os.environ['TEMP'] = str(scratch)
    tempfile.tempdir = str(scratch)
    sys.path[:0] = [str(ROOT.parent), str(ROOT)]
    suite = unittest.defaultTestLoader.discover(str(ROOT), pattern='test_*.py', top_level_dir=str(ROOT.parent))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
