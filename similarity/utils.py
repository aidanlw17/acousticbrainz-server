import os
from index_model import AnnoyModel
from collections import defaultdict

NORMALIZATION_SAMPLE_SIZE = 10000
PROCESS_BATCH_SIZE = 10000
QUERY_PADDING_FACTOR = 3
QUERY_RESULT_SIZE = 1000


def get_all_indices(n_trees=10):
    """Returns a dictionary of the indices that must be built for the
    specified distance measures and metrics"""
    distance_measures = [
        "angular",
        "manhattan"]
    metrics = ["mfccs",
               "mfccsw",
               "gfccs",
               "gfccsw",
               "key",
               "bpm",
               "onsetrate",
               "moods",
               "instruments",
               "dortmund",
               "rosamerica",
               "tzanetakis"]
    indices = defaultdict(list)
    for distance in distance_measures:
        for metric in metrics:
            indices[distance].append((metric, n_trees))
    return indices


def load_index_model(metric, n_trees=10, distance_type="angular"):
    """Loads an existing model for an Annoy index."""
    index = AnnoyModel(metric, n_trees=n_trees, distance_type=distance_type, load_existing=True)
    return index


def remove_index(metric, n_trees=10, distance_type="angular"):
    """Deletes the static index originally saved when an index is computed."""
    file_path = os.path.join(os.getcwd(), 'annoy_indices')
    name = '_'.join([metric, distance_type, str(n_trees)]) + '.ann'
    full_path = os.path.join(file_path, name)
    if os.path.exists(full_path):
        os.remove(full_path)
