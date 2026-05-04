from typing import List, Dict, Tuple
import numpy as np
from sklearn.cluster import DBSCAN
from loguru import logger


class ClusteringService:
    def __init__(self, eps: float = 0.25, min_samples: int = 2):
        """
        Args:
            eps: Maximum distance between two samples for them to be considered neighbors.
                 For cosine similarity, 0.25 roughly means > 75% similarity.
            min_samples: Minimum number of samples in a neighborhood to form a cluster.
        """
        self.eps = eps
        self.min_samples = min_samples

    def cluster(self, embeddings: List[List[float]]) -> Tuple[List[int], Dict[int, List[int]]]:
        """
        Cluster embeddings and return labels + cluster mapping.

        Returns:
            labels: List of cluster IDs for each embedding (-1 = noise/outlier)
            clusters: Dict mapping cluster_id -> list of embedding indices
        """
        if len(embeddings) < self.min_samples:
            logger.warning(f"Not enough samples ({len(embeddings)}) for clustering")
            return [-1] * len(embeddings), {}

        X = np.array(embeddings)

        # DBSCAN with cosine metric
        clustering = DBSCAN(
            eps=self.eps,
            min_samples=self.min_samples,
            metric="cosine",
        )
        labels = clustering.fit_predict(X)

        # Build cluster mapping (ignore -1 noise)
        clusters: Dict[int, List[int]] = {}
        for idx, label in enumerate(labels):
            if label != -1:
                clusters.setdefault(label, []).append(idx)

        n_clusters = len(clusters)
        n_noise = list(labels).count(-1)
        logger.info(f"Clustering complete: {n_clusters} clusters, {n_noise} outliers from {len(embeddings)} articles")

        return labels.tolist(), clusters

    def compute_centroid(self, embeddings: List[List[float]]) -> List[float]:
        """Compute the centroid (mean vector) of a cluster."""
        return np.mean(np.array(embeddings), axis=0).tolist()
