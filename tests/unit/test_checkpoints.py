import os
import unittest
from unittest.mock import patch

from workflows.checkpoints import Checkpoints, configured_checkpoints


class CheckpointConfigTests(unittest.TestCase):
    def test_explicit_backend_and_secret_not_in_repr(self):
        with patch.dict(os.environ, {"CHECKPOINT_BACKEND": "postgres",
                                    "CHECKPOINT_POSTGRES_DSN": "secret_dsn"}, clear=True):
            config = configured_checkpoints()
            self.assertEqual(config.backend, "postgres")
            self.assertNotIn("secret_dsn", repr(config))

    def test_missing_and_invalid_configuration_fail(self):
        for env in ({}, {"CHECKPOINT_BACKEND": "unknown"},
                    {"CHECKPOINT_BACKEND": "postgres"},
                    {"CHECKPOINT_BACKEND": "postgres", "CHECKPOINT_POSTGRES_DSN": ""}):
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True):
                with self.assertRaises((KeyError, ValueError)):
                    configured_checkpoints()

    def test_postgres_connections_do_not_run_migrations(self):
        with patch("workflows.checkpoints.PostgresSaver.from_conn_string") as factory:
            config = Checkpoints("postgres", "secret_dsn")
            with config.connect():
                pass
            factory.assert_called_once_with("secret_dsn")
            factory.return_value.__enter__.return_value.setup.assert_not_called()
            config.setup()
            factory.return_value.__enter__.return_value.setup.assert_called_once()
