"""PayTree first-opt protocol: prover, verifier, and client helpers."""

from __future__ import annotations

from .client import PaytreeFirstOpt
from .exceptions import NoSubTreeForSubPathError
from .prover import (
    Prover,
    ProverPaytreeFirstOpt,
    ProverState,
    prover_build_tree,
    prover_send_root,
)
from .prover_store import ProverRepo
from .verifier import (
    Verifier,
    verifier_receive_leaf_subproof_b64,
    verifier_receive_root_b64,
    verify_pruned_paytree_proof,
    verify_pruned_proof_and_update_repo_b64,
)
from .verifier_store import VerifierRepo, VerifierRepoBytes

__all__ = [
    "NoSubTreeForSubPathError",
    "PaytreeFirstOpt",
    "Prover",
    "ProverPaytreeFirstOpt",
    "ProverRepo",
    "ProverState",
    "Verifier",
    "VerifierRepo",
    "VerifierRepoBytes",
    "prover_build_tree",
    "prover_send_root",
    "verifier_receive_leaf_subproof_b64",
    "verifier_receive_root_b64",
    "verify_pruned_paytree_proof",
    "verify_pruned_proof_and_update_repo_b64",
]
