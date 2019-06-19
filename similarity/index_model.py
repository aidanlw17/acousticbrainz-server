import os

import similarity.exceptions

from annoy import AnnoyIndex
from sqlalchemy import text

class AnnoyModel(object):
    def __init__(self, connection, metric_name, n_trees=10, distance_type='angular', load_existing=False):
        """
        Args:
            - metric_name: the name of the metric that vectors in the index will 
              represent, a string.
            - n_trees: the number of trees used in building the index, a positive 
              integer. 
            - distance_type: distance measure, a string. Possibilities are 
              "angular", "euclidean", "manhattan", "hamming", or "dot".
        """
        self.connection = connection
        self.metric_name = metric_name
        self.n_trees = n_trees
        self.distance_type = distance_type
        self.dimension = self.get_vector_dimension()
        self.index = AnnoyIndex(self.dimension, metric=self.distance_type)
        
        # in_loaded_state set to True if the index is built, loaded, or saved.
        # At any of these points, items can no longer be added to the index.
        self.in_loaded_state = False
        if load_existing:
            self.load()


    def get_vector_dimension(self):
        """ 
        Get dimension of metric vectors. If there is no metric of this type
        already created then we need to raise an error.
        """
        result = self.connection.execute("""
            SELECT *
              FROM similarity
             LIMIT 1
        """)
        try:
            dimension = len(result.fetchone()[self.metric_name])
            return dimension
        except:
            raise ValueError("No existing metric named \"{}\"".format(metric_name))


    def build(self):
        self.index.build(self.n_trees)
        self.in_loaded_state = True


    def save(self, location=os.path.join(os.getcwd(), 'annoy_indices'), name=None):
        # Save and load the index using the metric name.
        try: 
            os.makedirs(location)
        except OSError:
            if not os.path.isdir(location):
                raise
        name = '_'.join([name or self.metric_name, self.distance_type, str(self.n_trees)]) + '.ann'
        file_path = os.path.join(location, name)
        self.index.save(file_path)
        self.in_loaded_state = True


    def load(self, name=None):
        """
        Args:
            name: name of the metric that should be loaded. If None, it will use the
            metric specified when initializing the index.
        Raises: 
            IndexNotFoundException: if there is no saved index with the given parameters.
        """
        # Load and build an existing annoy index.
        file_path = os.path.join(os.getcwd(), 'annoy_indices')
        name = '_'.join([name or self.metric_name, self.distance_type, str(self.n_trees)]) + '.ann'
        full_path = os.path.join(file_path, name)
        try: 
            self.index.load(full_path)
            self.in_loaded_state = True
        except:
            raise similarity.exceptions.IndexNotFoundException



    def add_recording_by_mbid(self, mbid, offset):
        """Add a single recording specified by (mbid, offset) to the index.
        Note that when adding a single recording, space is allocated for
        the lowlevel.id + 1 items.
        """
        if self.in_loaded_state:
            raise similarity.exceptions.CannotAddItemException

        query = text("""
            SELECT *
              FROM similarity
             WHERE id = (
                SELECT id
                  FROM lowlevel
                 WHERE gid = :mbid
                   AND submission_offset = :offset )
        """)
        result = self.connection.execute(query, { "mbid": mbid, "submission_offset": offset})
        row = result.fetchone()
        if row:
            recording_vector = row[self.metric_name]
            id = row['id']
            if not self.index.get_item_vector(id):
                self.index.add_item(id, recording_vector)


    def add_recording_by_id(self, id):
        """Add a single recording specified by its lowlevel.id to the index.
        Note that when adding a single recording, space is allocated for
        lowlevel.id + 1 items.
        """
        if self.in_loaded_state:
            raise similarity.exceptions.CannotAddItemException

        query = text("""
            SELECT *
              FROM similarity
             WHERE id = :id
        """)
        self.connection.execute(query, {"id": id})
        if not result.rowcount:
            raise similarity.exceptions.ItemNotFoundException
        row = result.fetchone()
        if not self.index.get_item_vector(id):
            self.index.add_item(row[id], row[self.metric_name])

 
    def add_recording_with_vector(self, id, vector):
        if self.in_loaded_state:
            raise similarity.exceptions.CannotAddItemException
        if not self.index.get_item_vector(id):
            self.index.add_item(id, vector)


    def get_nns_by_id(self, id, num_neighbours, return_ids=False):
        """Get the most similar recordings for a recording with the
           specified id.
        
        Args:
            id: non-negative integer lowlevel.id for a recording.
            num_neighbours: positive integer, number of similar recordings
            to be returned in the query.
            return_ids: boolean, determines whether (mbid, offset), or lowlevel.id
            is returned for each similar recording.
        Returns:
            return_ids = True: A list of lowlevel.ids [id1, ..., idn]
            return_ids = False: A list of tuples [(mbid1, offset), ..., (mbidn, offset)]
        """
        try:
            ids = self.index.get_nns_by_item(id, num_neighbours)
        except:
            raise similarity.exceptions.ItemNotFoundException
        if return_ids:
            # Return only ids
            return ids
        else:
            # Get corresponding (mbid, offset) for the most similar ids
            query = text("""
                SELECT id
                     , gid
                     , submission_offset
                  FROM lowlevel
                 WHERE id IN :ids
            """)
            result = self.connection.execute(query, { "ids": tuple(ids) })

            recordings = []
            for row in result.fetchall():
                recordings.append((row["gid"], row["submission_offset"]))

            return recordings

    def get_nns_by_mbid(self, mbid, offset, num_neighbours, return_ids=False):
        # Find corresponding lowlevel.id to (mbid, offset) combination,
        # then call get_nns_by_id
        mbid = mbid.lower()
        query = text("""
            SELECT id
              FROM lowlevel
             WHERE gid = :mbid
               AND submission_offset = :offset
        """)
        result = self.connection.execute(query, { "mbid": mbid, "offset": offset })
        if not result.rowcount:
            print("That (mbid, offset) combination does not exist")
        else:
            id = result.fetchone()[0]
            return self.get_nns_by_id(id, num_neighbours, return_ids)

"""
A dictionary to track the base indices that should be built.
Naming convention for a saved index is "<metric_name>_<distance_type>_<n_trees>.ann"
e.g. "mfccs_angular_10.ann"
Format of BASE_INDICES dictionary:
{"metric_name": [distance_type, n_trees]}
"""
BASE_INDICES = {
    "mfccs": {"distance_types": {"angular": {"n_trees": 10}}},
    "mfccsw": {"distance_types": {"angular": {"n_trees": 10}}},
    "gfccs": {"distance_types": {"angular": {"n_trees": 10}}},
    "gfccsw": {"distance_types": {"angular": {"n_trees": 10}}},
    "key": {"distance_types": {"angular": {"n_trees": 10}}},
    "bpm": {"distance_types": {"angular": {"n_trees": 10}}},
    "onsetrate": {"distance_types": {"angular": {"n_trees": 10}}},
    "moods": {"distance_types": {"angular": {"n_trees": 10}}},
    "instruments": {"distance_types": {"angular": {"n_trees": 10}}},
    "dortmund": {"distance_types": {"angular": {"n_trees": 10}}},
    "rosamerica": {"distance_types": {"angular": {"n_trees": 10}}},
    "tzanetakis": {"distance_types": {"angular": {"n_trees": 10}}}
}