"""
Test runner.

Usage (from the project root):
    .venv\\Scripts\\python.exe tests\\run_tests.py            # everything
    .venv\\Scripts\\python.exe tests\\run_tests.py unit       # one package
    .venv\\Scripts\\python.exe tests\\run_tests.py ml security

Exit code is non-zero when any test fails, so this is CI-ready.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PACKAGES = ("unit", "api", "security", "ml", "firebase")


def build_suite(packages):
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for pkg in packages:
        start_dir = str(ROOT / "tests" / pkg)
        suite.addTests(loader.discover(
            start_dir=start_dir, pattern="test_*.py", top_level_dir=str(ROOT)
        ))
    return suite


def main(argv):
    packages = [a for a in argv if a in PACKAGES] or list(PACKAGES)
    print("=" * 70)
    print("  Student Dropout Platform - test suite")
    print(f"  packages: {', '.join(packages)}")
    print("=" * 70)

    result = unittest.TextTestRunner(verbosity=2).run(build_suite(packages))

    print()
    print("=" * 70)
    print(f"  run:      {result.testsRun}")
    print(f"  failures: {len(result.failures)}")
    print(f"  errors:   {len(result.errors)}")
    print(f"  skipped:  {len(result.skipped)}")
    print("=" * 70)

    if result.failures or result.errors:
        print("\nFAILING CHECKS (each one is a reported defect):")
        for test, _ in result.failures:
            print(f"  [FAIL] {test.id()}")
        for test, _ in result.errors:
            print(f"  [ERROR] {test.id()}")

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
