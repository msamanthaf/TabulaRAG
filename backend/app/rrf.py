from typing import Iterable

def rrf_fuse(
    ranked_lists: list[list[str]],
    k: int = 60
) -> dict[str, float]:
    """
    ranked_lists: list of lists of IDs, each in rank order (best first).
    returns: id -> fused score
    """
    scores: dict[str, float] = {}
    for lst in ranked_lists:
        for rank, _id in enumerate(lst, start=1):
            scores[_id] = scores.get(_id, 0.0) + 1.0 / (k + rank)
    return scores
