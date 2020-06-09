import os
import json
import unittest
import mock
import uuid

from webserver.testing import AcousticbrainzTestCase
from webserver.views.api.v1 import similarity
from webserver.views.api.exceptions import APIBadRequest
from similarity.exceptions import IndexNotFoundException, ItemNotFoundException
from similarity.index_model import AnnoyModel
from webserver.testing import DB_TEST_DATA_PATH
from db.exceptions import NoDataFoundException


class APISimilarityViewsTestCase(AcousticbrainzTestCase):

    def setUp(self):
        super(APISimilarityViewsTestCase, self).setUp()
        self.uuid = str(uuid.uuid4())

        self.test_recording1_mbid = '0dad432b-16cc-4bf0-8961-fd31d124b01b'
        self.test_recording1_data_json = open(os.path.join(DB_TEST_DATA_PATH, self.test_recording1_mbid + '.json')).read()
        self.test_recording1_data = json.loads(self.test_recording1_data_json)

        self.test_recording2_mbid = 'e8afe383-1478-497e-90b1-7885c7f37f6e'
        self.test_recording2_data_json = open(os.path.join(DB_TEST_DATA_PATH, self.test_recording2_mbid + '.json')).read()
        self.test_recording2_data = json.loads(self.test_recording2_data_json)

    @mock.patch("webserver.views.api.v1.similarity.AnnoyModel")
    def test_get_similar_recordings_bad_uuid(self, annoy_model):
        """ URL Endpoint returns 404 because url-part doesn't match UUID.
            This error is raised by Flask, but we special-case to json.
        """
        resp = self.client.get("/api/v1/similarity/mfccs/nothing")
        self.assertEqual(404, resp.status_code)

        annoy_model.assert_not_called()
        expected_result = {"message": "The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again."}
        self.assertEqual(resp.json, expected_result)

    @mock.patch("webserver.views.api.v1.similarity.AnnoyModel")
    def test_get_similar_recordings_no_params(self, annoy_model):
        """When offset, distance, n_trees, and n_neighbours are not specified,
        they are set with default values. Metric must be specified.
        """
        metric = "mfccs"
        offset = 0
        distance_type = "angular"
        n_trees = 10
        n_neighbours = 200
        annoy_mock = mock.Mock()
        annoy_mock.get_nns_by_mbid.return_value = [[1, 2], [], [0.5, 0.5]]
        annoy_model.return_value = annoy_mock

        resp = self.client.get("/api/v1/similarity/{}/{}".format(metric, self.uuid))
        self.assertEqual(200, resp.status_code)

        annoy_model.assert_called_with(metric, n_trees=n_trees, distance_type=distance_type, load_existing=True)
        annoy_mock.get_nns_by_mbid.assert_called_with(self.uuid, offset, n_neighbours)

    @mock.patch("webserver.views.api.v1.similarity.AnnoyModel")
    def test_get_similar_recordings_invalid_params(self, annoy_model):
        # If offset is not integer >= 0, APIBadRequest is raised
        resp = self.client.get("/api/v1/similarity/mfccs/%s?n=x" % self.uuid)
        self.assertEqual(400, resp.status_code)

        # If index params are not in index_model.BASE_INDICES, they default.
        # If n_neighbours is larger than 1000, it defualts.
        annoy_mock = mock.Mock()
        annoy_mock.get_nns_by_mbid.return_value = [[1, 2], [], [0.5, 0.5]]
        annoy_model.return_value = annoy_mock
        resp = self.client.get("/api/v1/similarity/mfccs/%s?n_trees=-1&distance_type=7&n_neighbours=2000" % self.uuid)
        self.assertEqual(200, resp.status_code)

        offset = 0
        distance_type = "angular"
        n_trees = 10
        n_neighbours = 200
        metric = "mfccs"
        annoy_model.assert_called_with(metric, n_trees=n_trees, distance_type=distance_type, load_existing=True)
        annoy_mock.get_nns_by_mbid.assert_called_with(self.uuid, offset, n_neighbours)

        # If n_neighbours is not numerical, it defaults
        resp = self.client.get("/api/v1/similarity/mfccs/%s?n_trees=-1&distance_type=7&n_neighbours=x" % self.uuid)
        self.assertEqual(200, resp.status_code)

        annoy_model.assert_called_with(metric, n_trees=n_trees, distance_type=distance_type, load_existing=True)
        annoy_mock.get_nns_by_mbid.assert_called_with(self.uuid, offset, n_neighbours)

    @mock.patch("webserver.views.api.v1.similarity.AnnoyModel")
    def test_get_similar_recordings_invalid_metric(self, annoy_model):
        # If metric does not exist, APIBadRequest is raised.
        resp = self.client.get("/api/v1/similarity/nothing/%s" % self.uuid)
        self.assertEqual(400, resp.status_code)
        annoy_model.assert_not_called()
        expected_result = {"message": "An index with the specified metric does not exist."}
        self.assertEqual(expected_result, resp.json)

    @mock.patch("webserver.views.api.v1.similarity.AnnoyModel")
    def test_get_similar_recordings_index_errors(self, annoy_model):
        # If the (MBID, offset) combination is not submitted, APIBadRequest is raised.
        annoy_mock = mock.Mock()
        annoy_mock.get_nns_by_mbid.side_effect = NoDataFoundException
        annoy_model.return_value = annoy_mock
        resp = self.client.get("/api/v1/similarity/mfccs/%s?n=2" % self.uuid)
        self.assertEqual(400, resp.status_code)
        expected_result = {"message": "No submission exists for the given (MBID, offset) combination."}
        self.assertEqual(expected_result, resp.json)

        # If the (MBID, offset) is submitted but not yet indexed, APIBadRequest is raised.
        annoy_mock.get_nns_by_mbid.side_effect = ItemNotFoundException
        resp = self.client.get("/api/v1/similarity/mfccs/%s?n=2" % self.uuid)
        self.assertEqual(400, resp.status_code)
        expected_result = {"message": "The submission of interest is not indexed."}
        self.assertEqual(expected_result, resp.json)

        # If index does not load with given parameters, APIBadRequest is raised.
        annoy_model.side_effect = IndexNotFoundException
        resp = self.client.get("/api/v1/similarity/mfccs/%s" % self.uuid)
        self.assertEqual(400, resp.status_code)
        expected_result = {"message": "Index does not exist with specified parameters."}
        self.assertEqual(expected_result, resp.json)

    def test_get_many_similar_recordings_no_params(self):
        # No recording_ids parameter results in APIBadRequest.
        resp = self.client.get("/api/v1/similarity/mfccs")
        self.assertEqual(400, resp.status_code)
        expected_result = {"message": "Missing `recording_ids` parameter"}
        self.assertEqual(resp.json, expected_result)

    @mock.patch("webserver.views.api.v1.similarity.AnnoyModel")
    def test_get_many_similar_recordings(self, annoy_model):
        # Check that similar recordings are returned for many recordings,
        # including two offsets of the same MBID.
        params = "c5f4909e-1d7b-4f15-a6f6-1af376bc01c9;7f27d7a9-27f0-4663-9d20-2c9c40200e6d:3;405a5ff4-7ee2-436b-95c1-90ce8a83b359:2;405a5ff4-7ee2-436b-95c1-90ce8a83b359:3"
        expected_result = {
            "c5f4909e-1d7b-4f15-a6f6-1af376bc01c9": {"0": ["similar_rec1", "similar_rec2"]},
            "7f27d7a9-27f0-4663-9d20-2c9c40200e6d": {"3": ["similar_rec1", "similar_rec2"]},
            "405a5ff4-7ee2-436b-95c1-90ce8a83b359": {"2": ["similar_rec1", "similar_rec2"], "3": ["similar_rec1", "similar_rec2"]}
        }
        annoy_mock = mock.Mock()
        annoy_mock.get_bulk_nns_by_mbid.return_value = expected_result
        annoy_model.return_value = annoy_mock

        resp = self.client.get('api/v1/similarity/mfccs?recording_ids=' + params)
        self.assertEqual(200, resp.status_code)
        self.assertEqual(expected_result, resp.json)

        # Index parameters should default if not specified by query string.
        annoy_model.assert_called_with("mfccs", n_trees=10, distance_type="angular", load_existing=True)

        recordings = [("c5f4909e-1d7b-4f15-a6f6-1af376bc01c9", 0),
                      ("7f27d7a9-27f0-4663-9d20-2c9c40200e6d", 3),
                      ("405a5ff4-7ee2-436b-95c1-90ce8a83b359", 2),
                      ("405a5ff4-7ee2-436b-95c1-90ce8a83b359", 3)]

        annoy_mock.get_bulk_nns_by_mbid.assert_called_with(recordings, 200)

        # upper-case
        params = "c5f4909e-1d7b-4f15-a6f6-1AF376BC01C9"
        expected_result = {
            "c5f4909e-1d7b-4f15-a6f6-1af376bc01c9": {"0": ["similar_rec1", "similar_rec2"]}
        }
        annoy_mock.get_bulk_nns_by_mbid.return_value = expected_result

        # get_bulk_nns.return_value = expected_result
        resp = self.client.get('api/v1/similarity/mfccs?recording_ids=' + params)
        self.assertEqual(200, resp.status_code)
        self.assertEqual(resp.json, expected_result)

        # Recordings passed in should be lowercased when parsing.
        recordings = [("c5f4909e-1d7b-4f15-a6f6-1af376bc01c9", 0)]
        annoy_mock.get_bulk_nns_by_mbid.assert_called_with(recordings, 200)

    @mock.patch("webserver.views.api.v1.similarity.AnnoyModel")
    def test_get_many_similar_recordings_missing_mbid(self, annoy_model):
        # Check that within a set of mbid parameters, the ones absent
        # from the database are ignored.
        recordings = "c5f4909e-1d7b-4f15-a6f6-1af376bc01c9;7f27d7a9-27f0-4663-9d20-2c9c40200e6d:3;405a5ff4-7ee2-436b-95c1-90ce8a83b359:2"
        end = "&n_trees=-1&distance_type=x&n_neighbours=2000"
        expected_result = {
            "c5f4909e-1d7b-4f15-a6f6-1af376bc01c9": {"0": ["similar_rec1", "similar_rec2"]},
            "405a5ff4-7ee2-436b-95c1-90ce8a83b359": {"2": ["similar_rec1", "similar_rec2"]}
        }
        annoy_mock = mock.Mock()
        annoy_mock.get_bulk_nns_by_mbid.return_value = expected_result
        annoy_model.return_value = annoy_mock

        resp = self.client.get("/api/v1/similarity/mfccs?recording_ids=" + recordings + end)
        self.assertEqual(200, resp.status_code)
        self.assertEqual(expected_result, resp.json)

        # If index parameters are invalid, they are defaulted.
        annoy_model.assert_called_with("mfccs", n_trees=10, distance_type="angular", load_existing=True)

        recordings = [("c5f4909e-1d7b-4f15-a6f6-1af376bc01c9", 0),
                      ("7f27d7a9-27f0-4663-9d20-2c9c40200e6d", 3),
                      ("405a5ff4-7ee2-436b-95c1-90ce8a83b359", 2)]
        annoy_mock.get_bulk_nns_by_mbid.assert_called_with(recordings, 200)

    def test_get_many_similar_recordings_more_than_200(self):
        # Check that a request for over 200 recordings raises an error.
        manyids = [str(uuid.uuid4()) for i in range(26)]
        limit_exceed_url = ";".join(manyids)
        resp = self.client.get("/api/v1/similarity/mfccs?recording_ids=" + limit_exceed_url)
        self.assertEqual(400, resp.status_code)
        expected_result = {"message": "More than 25 recordings not allowed per request"}
        self.assertEqual(expected_result, resp.json)

    @mock.patch("webserver.views.api.v1.similarity.AnnoyModel")
    def test_get_similarity_between_no_params(self, annoy_model):
        # If no index params are provided, they default.
        # Submissions can be selected using offset.
        recordings = "c5f4909e-1d7b-4f15-a6f6-1af376bc01c9;7f27d7a9-27f0-4663-9d20-2c9c40200e6d:2"
        rec_1 = ("c5f4909e-1d7b-4f15-a6f6-1af376bc01c9", 0)
        rec_2 = ("7f27d7a9-27f0-4663-9d20-2c9c40200e6d", 2)

        annoy_mock = mock.Mock()
        annoy_mock.get_similarity_between.return_value = 1
        annoy_model.return_value = annoy_mock

        resp = self.client.get("/api/v1/similarity/mfccs/between?recording_ids=" + recordings)
        self.assertEqual(200, resp.status_code)
        self.assertEqual({"mfccs": 1}, resp.json)

        annoy_model.assert_called_with("mfccs", n_trees=10, distance_type="angular", load_existing=True)
        annoy_mock.get_similarity_between.assert_called_with(rec_1, rec_2)

    @mock.patch("webserver.views.api.v1.similarity.AnnoyModel")
    def test_get_similarity_between_exceptions(self, annoy_model):
        # If there is no submission for an (MBID, offset) combination,
        # empty dictionary is returned.
        annoy_mock = mock.Mock()
        annoy_mock.get_similarity_between.side_effect = NoDataFoundException
        annoy_model.return_value = annoy_mock

        recordings = "c5f4909e-1d7b-4f15-a6f6-1af376bc01c9;7f27d7a9-27f0-4663-9d20-2c9c40200e6d:2"
        resp = self.client.get("/api/v1/similarity/mfccs/between?recording_ids=" + recordings)
        self.assertEqual(200, resp.status_code)

        expected_result = {}
        self.assertEqual(expected_result, resp.json)

        # If item is not yet loaded in index, returns empty dictionary.
        annoy_mock.get_similarity_between.side_effect = ItemNotFoundException
        resp = self.client.get("/api/v1/similarity/mfccs/between?recording_ids=" + recordings)
        self.assertEqual(200, resp.status_code)
        self.assertEqual(expected_result, resp.json)

        # If index is unable to load, APIBadRequest is raised.
        annoy_model.side_effect = IndexNotFoundException
        resp = self.client.get("/api/v1/similarity/mfccs/between?recording_ids=" + recordings)
        self.assertEqual(400, resp.status_code)

        expected_result = {"message": "Index does not exist with specified parameters."}
        self.assertEqual(expected_result, resp.json)

    def test_get_similarity_between_no_recordings(self):
        # Without recording_ids parameter, APIBadRequest is raised.
        resp = self.client.get("/api/v1/similarity/mfccs/between")
        self.assertEqual(400, resp.status_code)
        expected_result = {"message": "Missing `recording_ids` parameter"}
        self.assertEqual(expected_result, resp.json)

        # If more or less than 2 recordings are specified, APIBadRequest is raised.
        recordings = "c5f4909e-1d7b-4f15-a6f6-1af376bc01c9"
        resp = self.client.get("/api/v1/similarity/mfccs/between?recording_ids=" + recordings)
        self.assertEqual(400, resp.status_code)
        expected_result = {"message": "Does not contain 2 recordings in the request"}
        self.assertEqual(expected_result, resp.json)

        recordings = "c5f4909e-1d7b-4f15-a6f6-1af376bc01c9;7f27d7a9-27f0-4663-9d20-2c9c40200e6d;405a5ff4-7ee2-436b-95c1-90ce8a83b359"
        resp = self.client.get("/api/v1/similarity/mfccs/between?recording_ids=" + recordings)
        self.assertEqual(400, resp.status_code)
        expected_result = {"message": "Does not contain 2 recordings in the request"}
        self.assertEqual(expected_result, resp.json)


class SimilarityValidationTest(unittest.TestCase):

    def test_check_index_params(self):
        # If metric does not exist, APIBadRequest is raised.
        metric = "x"
        with self.assertRaises(APIBadRequest) as ex:
            similarity._check_index_params(metric)
        self.assertEqual(str(ex.exception), "An index with the specified metric does not exist.")
