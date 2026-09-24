"""Run the application recovery suite with real PostgreSQL checkpoints.

Requires an isolated test database. Synthetic checkpoint records are retained.
Missing configuration is an error, never a skipped/passing deployment gate.
"""
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integration"))
from test_journey import JourneyTests
from fastapi.testclient import TestClient
from apps.api.main import create_app
from apps.service import Application
from apps.storage import Store
from adapters.insurance.synthetic import SyntheticCore
from workflows.checkpoints import Checkpoints


class PostgresJourneyTests(JourneyTests):
    @classmethod
    def setUpClass(cls):
        cls.checkpoints = Checkpoints("postgres", os.environ["CHECKPOINT_TEST_POSTGRES_DSN"])
        cls.checkpoints.setup()

    def restart(self):
        self.core = SyntheticCore("tests/fixtures/local_fixtures.json", self.core_path)
        self.application = Application(Store(self.app_path), self.core,
                                       checkpoints=self.checkpoints)
        self.client = TestClient(create_app(self.application, self.identities))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PostgresJourneyTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
