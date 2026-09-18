"""Tests for the /preview page: public access, staleness, failures.

The route serves a generated artifact and regenerates it on demand, so these
tests sandbox the frontend directory, the source roster and the generator - the
real 2 MB `frontend/dashboard_preview.html` is never read, written or deleted.
"""
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

import backend.app as app_module
import src.generate_dashboard_preview as preview_generator
from tests.base import AppTestCase

PREVIEW_FILENAME = "dashboard_preview.html"
SENTINEL = "<!doctype html><title>preview</title><body>preview-body</body>"


class PreviewPageTestCase(AppTestCase):
    """Base case: point the route at a throwaway frontend directory."""

    def setUp(self):
        super().setUp()
        self.frontend_dir = Path(self.tmpdir) / "frontend"
        self.frontend_dir.mkdir()
        self._orig_frontend_dir = app_module.FRONTEND_DIR
        app_module.FRONTEND_DIR = self.frontend_dir
        self.preview_path = self.frontend_dir / PREVIEW_FILENAME

    def tearDown(self):
        app_module.FRONTEND_DIR = self._orig_frontend_dir
        super().tearDown()

    def write_preview(self):
        self.preview_path.write_text(SENTINEL, encoding="utf-8")

    def patch_roster(self, mtime):
        """Point the staleness check at a controlled source roster."""
        roster = Path(self.tmpdir) / "student_risk_scores.csv"
        roster.write_text("Student_ID\n", encoding="utf-8")
        os.utime(roster, (mtime, mtime))
        patcher = mock.patch.object(preview_generator, "ROSTER_CSV", roster)
        patcher.start()
        self.addCleanup(patcher.stop)
        return roster


class TestPublicAccess(PreviewPageTestCase):
    """The preview is public so it can be linked from the login page."""

    def test_anonymous_can_open_the_preview(self):
        self.write_preview()
        self.patch_roster(time.time() - 100)
        response = self.client.get("/preview")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"preview-body", response.data)

    def test_anonymous_request_triggers_generation(self):
        self.assertFalse(self.preview_path.exists())

        def fake_generate():
            self.write_preview()

        with mock.patch.object(preview_generator, "main", side_effect=fake_generate):
            response = self.client.get("/preview")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.preview_path.is_file())


class TestLoginPageLink(AppTestCase):
    """Discoverability: the login page links to the public preview."""

    def test_login_page_links_to_the_preview(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'href="/preview"', response.data)


class TestPreviewTemplate(unittest.TestCase):
    """The generated page must offer a way back to sign-in."""

    def test_template_links_back_to_login(self):
        self.assertIn('href="/login"', preview_generator.TEMPLATE)


class TestAutoGeneration(PreviewPageTestCase):
    def test_missing_file_is_generated_on_demand(self):
        self.assertFalse(self.preview_path.exists())
        calls = []

        def fake_generate():
            calls.append(1)
            self.write_preview()

        with mock.patch.object(preview_generator, "main", side_effect=fake_generate):
            response = self.client.get("/preview")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"preview-body", response.data)
        self.assertEqual(len(calls), 1, "generator should run exactly once")
        self.assertTrue(self.preview_path.is_file())

    def test_existing_file_is_served_without_regenerating(self):
        self.write_preview()
        self.patch_roster(time.time() - 100)
        with mock.patch.object(preview_generator, "main") as generator:
            response = self.client.get("/preview")
        self.assertEqual(response.status_code, 200)
        generator.assert_not_called()


class TestStaleness(PreviewPageTestCase):
    """The page is refreshed when the roster it renders is newer."""

    def test_newer_roster_forces_regeneration(self):
        self.write_preview()
        self.patch_roster(time.time() + 10)
        calls = []

        def fake_generate():
            calls.append(1)
            self.write_preview()

        with mock.patch.object(preview_generator, "main", side_effect=fake_generate):
            response = self.client.get("/preview")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 1, "a stale page should be regenerated")

    def test_up_to_date_preview_is_not_regenerated(self):
        self.write_preview()
        self.patch_roster(time.time() - 100)
        with mock.patch.object(preview_generator, "main") as generator:
            response = self.client.get("/preview")
        self.assertEqual(response.status_code, 200)
        generator.assert_not_called()

    def test_missing_roster_does_not_force_regeneration(self):
        """Nothing to rebuild from, so the existing page is served as-is."""
        self.write_preview()
        missing = Path(self.tmpdir) / "does-not-exist.csv"
        patcher = mock.patch.object(preview_generator, "ROSTER_CSV", missing)
        patcher.start()
        self.addCleanup(patcher.stop)

        with mock.patch.object(preview_generator, "main") as generator:
            response = self.client.get("/preview")

        self.assertEqual(response.status_code, 200)
        generator.assert_not_called()


class TestGenerationFailures(PreviewPageTestCase):
    def _get_with_generator_error(self, exc):
        with mock.patch.object(preview_generator, "main", side_effect=exc):
            return self.client.get("/preview")

    def test_missing_roster_reports_the_scoring_step(self):
        response = self._get_with_generator_error(FileNotFoundError("no csv"))
        self.assertEqual(response.status_code, 503)
        self.assertIn("student_risk_scores.csv", response.get_data(as_text=True))

    def test_generator_crash_returns_a_503(self):
        response = self._get_with_generator_error(RuntimeError("boom"))
        self.assertEqual(response.status_code, 503)
        self.assertIn("could not be generated", response.get_data(as_text=True))

    def test_generator_that_writes_nothing_returns_a_503(self):
        with mock.patch.object(preview_generator, "main", return_value=None):
            response = self.client.get("/preview")
        self.assertEqual(response.status_code, 503)
        self.assertIn("did not produce a file", response.get_data(as_text=True))

    def test_unimportable_generator_returns_a_503(self):
        # `None` in sys.modules makes the deferred import fail.
        with mock.patch.dict(
            sys.modules, {"src.generate_dashboard_preview": None}
        ):
            response = self.client.get("/preview")
        self.assertEqual(response.status_code, 503)
        self.assertIn("could not be imported", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
