from __future__ import absolute_import

import mock

import db.exceptions
from webserver.testing import ServerTestCase
from db.testing import TEST_DATA_PATH
from flask import url_for
import os


class LegacyViewsTestCase(ServerTestCase):

    def test_submit_low_level(self):
        mbid = '0dad432b-16cc-4bf0-8961-fd31d124b01b'

        with open(os.path.join(TEST_DATA_PATH, mbid + '.json')) as json_file:
            with self.app.test_client() as client:
                sub_resp = client.post("/%s/low-level" % mbid,
                                       data=json_file.read(),
                                       content_type='application/json')
                self.assertEqual(sub_resp.status_code, 200)

        # Getting from the new API
        resp = self.client.get("/api/v1/%s/low-level" % mbid)
        self.assertEqual(resp.status_code, 200)

    def test_get_low_level(self):
        mbid = '0dad432b-16cc-4bf0-8961-fd31d124b01b'
        resp = self.client.get(url_for('api.get_low_level', mbid=mbid))
        self.assertEqual(resp.status_code, 404)

        self.load_low_level_data(mbid)

        resp = self.client.get(url_for('api.get_low_level', mbid=mbid))
        self.assertEqual(resp.status_code, 200)

        # works regardless of the case of the uuid
        resp = self.client.get(url_for('api.get_low_level', mbid=mbid.upper()))
        self.assertEqual(resp.status_code, 200)

    @mock.patch('db.data.load_high_level')
    def test_get_high_level(self, load_high_level):
        mbid = '0dad432b-16cc-4bf0-8961-fd31d124b01b'
        load_high_level.side_effect = db.exceptions.NoDataFoundException
        resp = self.client.get(url_for('api.get_high_level', mbid=mbid))
        self.assertEqual(resp.status_code, 404)

        load_high_level.side_effect = None
        load_high_level.return_value = '{}'

        resp = self.client.get(url_for('api.get_high_level', mbid=mbid))
        self.assertEqual(resp.status_code, 200)
        load_high_level.assert_called_with(mbid, 0)

        resp = self.client.get(url_for('api.get_high_level', mbid=mbid.upper()))
        self.assertEqual(resp.status_code, 200)

    def test_count(self):
        mbid = '0dad432b-16cc-4bf0-8961-fd31d124b01b'
        resp = self.client.get(url_for('api.count', mbid=mbid))
        expected = {'mbid': mbid, 'count': 0}
        self.assertEqual(resp.status_code, 200)
        self.assertItemsEqual(resp.json, expected)

        self.load_low_level_data(mbid)
        expected = {'mbid': mbid, 'count': 1}
        resp = self.client.get(url_for('api.count', mbid=mbid))
        self.assertEqual(resp.status_code, 200)
        self.assertItemsEqual(resp.json, expected)

        # upper-case
        resp = self.client.get(url_for('api.count', mbid=mbid.upper()))
        self.assertEqual(resp.status_code, 200)
        # mbid stays lower-case in the response
        self.assertItemsEqual(resp.json, expected)

    def test_cors_headers(self):
        mbid = '0dad432b-16cc-4bf0-8961-fd31d124b01b'
        self.load_low_level_data(mbid)

        resp = self.client.get(url_for('api.get_low_level', mbid=mbid))
        self.assertEqual(resp.headers['Access-Control-Allow-Origin'], '*')
