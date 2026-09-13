"""Real Chromium journey with temporary stores and an in-process local worker."""
from contextlib import closing
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import uvicorn
from playwright.sync_api import sync_playwright, expect
from apps.api.main import create_app
from apps.service import Application
from apps.storage import Store
from adapters.insurance.synthetic import SyntheticCore


class BrowserTests(unittest.TestCase):
    def test_customer_receipt_and_employee_review(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,
                AUTO_RULES_PATH='policies/auto_synthetic_v1.json', CATALOGS_PATH='policies/local_catalogs_v1.json'):
            application = Application(Store(str(Path(folder) / 'app.db')),
                                      SyntheticCore('policies/local_fixtures.json', str(Path(folder) / 'core.db')))
            app = create_app(application, {'customer': {'subject': 'customer_one', 'role': 'customer'},
                                          'employee': {'subject': 'employee_one', 'role': 'employee'}})
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
                thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
                thread.start()
                try:
                    deadline = time.monotonic() + 10
                    while not server.started:
                        if time.monotonic() > deadline:
                            self.fail('Local server did not start')
                        time.sleep(.05)
                    with sync_playwright() as p, closing(p.chromium.launch()) as browser:
                        page = browser.new_page()
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.goto('http://127.0.0.1:' + str(sock.getsockname()[1]))
                        page.locator('#help').click()
                        expect(page.locator('#help_result')).to_contain_text('Priority:')
                        page.locator('#token').fill('customer')
                        page.locator('#create').click()
                        expect(page.locator('#draft')).to_contain_text('draft_version')
                        values = {'policy_ref': 'synthetic_policy', 'incident_at': '2026-09-12T10:00:00-04:00',
                                  'description': 'Parked vehicle struck', 'location_ref': 'synthetic_location',
                                  'vehicle_ref': 'synthetic_vehicle', 'contact_ref': 'synthetic_contact'}
                        for name, value in values.items():
                            page.locator('#' + name).fill(value)
                        page.locator('#injury_reported').select_option('no')
                        page.locator('#drivable').select_option('yes')
                        page.locator('#accurate').check()
                        page.locator('#save').click()
                        expect(page.locator('#notice')).to_contain_text('Queued')
                        self.assertTrue(application.work_once())
                        page.locator('#refresh').click()
                        expect(page.locator('#draft')).to_contain_text('awaiting_confirmation')
                        page.locator('#confirm').click()
                        expect(page.locator('#notice')).to_contain_text('Submission queued')
                        self.assertTrue(application.work_once())
                        page.locator('#refresh').click()
                        expect(page.locator('#draft')).to_contain_text('received')
                        page.locator('#token').fill('employee')
                        page.locator('#reviews').click()
                        cards = page.locator('#queue section')
                        expect(cards.first).to_be_visible()
                        for card in cards.all():
                            card.locator('textarea').fill('Reviewed synthetic report')
                            card.get_by_role('button', name='accept', exact=True).click()
                            expect(card.locator('pre')).to_contain_text('assignment_confirmed')
                        page.locator('#token').fill('customer')
                        page.locator('#resume').click()
                        expect(page.locator('#draft')).to_contain_text('review_completed')
                        self.assertEqual(errors, [])
                finally:
                    server.should_exit = True
                    thread.join(timeout=10)
