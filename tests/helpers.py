"""Shared, cached dataset so every test uses the same (small, fast) generated data."""
from functools import lru_cache
from database.generator.build import generate_all
from database.generator.config import Config, SCALES


@lru_cache(maxsize=None)
def dataset(seed=20261022, scale="tiny"):
    return generate_all(Config(seed=seed, **SCALES[scale]))


def clone_tables(R):
    return {k: v.copy() for k, v in R["tables"].items()}
