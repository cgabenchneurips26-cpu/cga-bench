"""Seed manager for reproducibility."""
import os
import random


def fix_all_seeds(seed: int = 42) -> None:
    """Fix all random seeds for deterministic execution."""
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import numpy
        numpy.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


if __name__ == "__main__":
    fix_all_seeds()
    print(f"All seeds fixed to 42")
