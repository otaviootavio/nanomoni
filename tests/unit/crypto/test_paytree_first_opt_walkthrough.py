"""Prover–verifier walkthrough: simplest flow with Merkle tree storage.

Both prover and verifier have their own Merkle tree storage (key–value).
Flow: prover builds 8-leaf tree, fills storages, sends root to verifier;
verifier stores root; prover prepares proof for leaf (secret + siblings)
and sends to verifier; verifier verifies, stores only siblings in node store
(secret lives in another repo), dumps tree.
"""

from __future__ import annotations

from nanomoni.crypto.merkle_index import (
    get_sibling_keys_eytzinger,
    get_sibling_position_at_level,
    key_eytzinger,
)
from nanomoni.crypto.merkle_tree import (
    build_merkle_proof_indexes_for_leaf_a_given_ancestor_b,
    build_merkle_tree,
    build_node_from_dependencies,
    get_proof_dependency_indexes,
    hash_bytes,
)
from nanomoni.protocol import (
    infer_subroot_index_for_incoming_pruned_merkle_proof,
    proof_indexes_first_opt,
    proof_indexes_standard,
    subroot_index_standard,
    verify_proof,
)

# ---------------------------------------------------------------------------
# Constants (parametrized at top of file)
# ---------------------------------------------------------------------------


# Hardcoded leaf secrets (preimages); leaf hash = hash_bytes(secret).
LEAF_SECRETS: tuple[bytes, ...] = (
    b"leaf0",
    b"leaf1",
    b"leaf2",
    b"leaf3",
    b"leaf4",
    b"leaf5",
    b"leaf6",
    b"leaf7",
)

NUM_LEAVES = len(LEAF_SECRETS)
DEPTH = (NUM_LEAVES).bit_length() - 1

# Placeholder for missing nodes when dumping sparse storage.
_MISSING_NODE = b"\x00" * 32


def _leaf_index_to_binary(i: int, num_bits: int = 3) -> str:
    """Leaf index to binary key: 0 -> '000', 1 -> '001', ..., 7 -> '111'."""
    return format(i, f"0{num_bits}b")


# ---------------------------------------------------------------------------
# Merkle node storage (prover and verifier share this type)
# ---------------------------------------------------------------------------


def _node_key(level: int, position: int, depth: int) -> str:
    """Eytzinger (binary) key for node at (level, position)."""
    return key_eytzinger(level, position, depth)


class MerkleNodeStore(dict[str, bytes]):
    """Merkle tree node storage: Eytzinger binary key -> node hash. Dumpable as ASCII tree."""

    def _infer_depth(self) -> int:
        """Depth inferred from key width (Eytzinger keys have length depth+1); 0 if empty."""
        if not self:
            return 0
        first_key = next(iter(self.keys()))
        return len(first_key) - 1

    def to_tree_levels(self) -> list[list[bytes]]:
        """Reconstruct tree levels from stored nodes; use placeholder for missing."""
        depth = self._infer_depth()
        if depth == 0 and not self:
            return []
        levels: list[list[bytes]] = []
        for level in range(depth + 1):
            n_pos = 1 << (depth - level)
            row = [
                self.get(_node_key(level, pos, depth), _MISSING_NODE)
                for pos in range(n_pos)
            ]
            levels.append(row)
        return levels


# ---------------------------------------------------------------------------
# Prover: two key–value storages
# ---------------------------------------------------------------------------


class ProverSecretStore(dict[str, bytes]):
    """Prover storage: binary_key -> secret. Keys 000..111 for 8 leaves."""

    pass


class ProverNodeStore(MerkleNodeStore):
    """Prover Merkle node storage: full tree, Eytzinger binary keys."""

    pass


def build_prover_storages(
    num_leaves: int,
    leaf_secrets: tuple[bytes, ...],
) -> tuple[ProverSecretStore, ProverNodeStore, bytes]:
    """Build Merkle tree, fill prover secret and node stores; return root and tree_levels."""
    assert num_leaves == len(leaf_secrets)
    depth = (num_leaves).bit_length() - 1
    num_bits = depth

    secret_store: ProverSecretStore = ProverSecretStore()
    for i in range(num_leaves):
        secret_store[_leaf_index_to_binary(i, num_bits)] = leaf_secrets[i]

    leaves = [hash_bytes(s) for s in leaf_secrets]
    root, tree_levels = build_merkle_tree(leaves)

    node_store: ProverNodeStore = ProverNodeStore()
    for level, row in enumerate(tree_levels):
        for position, h in enumerate(row):
            node_store[_node_key(level, position, depth)] = h

    return secret_store, node_store, root


# ---------------------------------------------------------------------------
# Verifier: Merkle tree storage (same type as prover node store)
# ---------------------------------------------------------------------------


class VerifierNodeStore(MerkleNodeStore):
    """Verifier Merkle node storage: root (and proof nodes); Eytzinger binary keys."""

    pass


class VerifierSecretStore(dict[str, bytes]):
    """Verifier storage: binary_key -> secret. Keys 000..111 for 8 leaves. Analogous to ProverSecretStore."""

    pass


# ---------------------------------------------------------------------------
# Payment index stores (prover: sent indexes, verifier: received indexes)
# ---------------------------------------------------------------------------


class ProverSentIndexStore:
    """Stores leaf indexes of payments the prover has sent."""

    def __init__(self) -> None:
        self._indexes: list[int] = []

    def add(self, leaf_index: int) -> None:
        """Record that the prover sent a proof for this leaf index."""
        self._indexes.append(leaf_index)

    def get_all(self) -> list[int]:
        """Return all sent leaf indexes (in order)."""
        return list(self._indexes)


class VerifierReceivedIndexStore:
    """Stores leaf indexes of payments the verifier has received and verified."""

    def __init__(self) -> None:
        self._indexes: list[int] = []

    def add(self, leaf_index: int) -> None:
        """Record that the verifier received and verified a proof for this leaf index."""
        self._indexes.append(leaf_index)

    def get_all(self) -> list[int]:
        """Return all received leaf indexes (in order)."""
        return list(self._indexes)


# ---------------------------------------------------------------------------
# Auditor (standard protocol): receives root at setup, validates proof at end
# ---------------------------------------------------------------------------


class AuditorState:
    """Auditor state for standard protocol: stores root, validates proof against it."""

    def __init__(self) -> None:
        self._root: bytes | None = None
        self._depth: int = 0

    def receive_tree(self, root: bytes, depth: int) -> None:
        """Store root and depth (mocked: prover sends Merkle tree to auditor)."""
        self._root = root
        self._depth = depth

    def validate_proof(
        self,
        secret: bytes,
        leaf_index: int,
        siblings: list[bytes],
    ) -> None:
        """Verify proof against stored root. Raises ValueError if invalid."""
        if self._root is None:
            raise ValueError("Auditor has no stored root")
        verify_proof(
            secret,
            leaf_index,
            siblings,
            self._root,
            subroot_index_standard(self._depth),
            self._depth,
        )


def verifier_store_root(store: VerifierNodeStore, root: bytes, depth: int) -> None:
    """Verifier stores the received Merkle root at (depth, 0)."""
    store[_node_key(depth, 0, depth)] = root


def verifier_store_proof(
    store: VerifierNodeStore,
    leaf_index: int,
    siblings: list[bytes],
    depth: int,
) -> None:
    """Store only siblings from a verified proof. Secret (leaf) is stored in another repo."""
    for level, sib in enumerate(siblings):
        sib_pos = get_sibling_position_at_level(leaf_index, level)
        store[_node_key(level, sib_pos, depth)] = sib


def verifier_stores_secret(
    secret_store: VerifierSecretStore,
    leaf_index: int,
    secret: bytes,
    depth: int,
) -> None:
    """Store only the leaf secret in the verifier secret store (analogous to verifier_store_proof for siblings)."""
    secret_store[_leaf_index_to_binary(leaf_index, depth)] = secret


def _lookup_sibling_hashes(
    store: MerkleNodeStore,
    indexes: list[tuple[int, int]],
    depth: int,
) -> list[bytes]:
    """Convert sibling indexes to node hashes via store lookup."""
    siblings: list[bytes] = []
    for level, pos in indexes:
        k = _node_key(level, pos, depth)
        h = store.get(k)
        if h is None:
            raise KeyError(f"missing node {k} in store")
        siblings.append(h)
    return siblings


def batch_get_node_hashes_or_secrets(
    node_store: MerkleNodeStore,
    secret_store: VerifierSecretStore,
    dependency_indexes: list[tuple[int, int]],
    depth: int,
) -> dict[tuple[int, int], bytes]:
    """Load all requested (level, pos) in one batch: node store and leaf secrets.

    For each (level, pos): use node store if present; for level 0 missing from
    node store, use secret store and return hash_bytes(secret). Real
    implementation would do a single DB/cache call for nodes and one for secrets.
    """
    result: dict[tuple[int, int], bytes] = {}
    for level, pos in dependency_indexes:
        key = _node_key(level, pos, depth)
        h = node_store.get(key)
        if h is not None:
            result[(level, pos)] = h
        elif level == 0:
            secret = secret_store.get(_leaf_index_to_binary(pos, depth))
            if secret is not None:
                result[(level, pos)] = hash_bytes(secret)
    return result


def _run_standard_setup(
    num_leaves: int,
    leaf_secrets: tuple[bytes, ...],
) -> tuple[
    ProverSecretStore,
    ProverNodeStore,
    bytes,
    VerifierNodeStore,
    VerifierSecretStore,
    int,
]:
    """Build prover/verifier stores, send root to verifier. Returns stores and depth."""
    depth = (num_leaves).bit_length() - 1

    # [Setup][Crypto] Build Merkle tree: hash leaf secrets, combine levels up to root.
    # [Setup][Storage] Write prover secret store (leaf_key -> secret) and node store (Eytzinger key -> hash).
    prover_secrets, prover_nodes, root = build_prover_storages(num_leaves, leaf_secrets)
    print("[Setup][Crypto] Prover builds Merkle tree from leaf secrets; compute root.")
    print(
        "[Setup][Storage] Prover saves secret store and full node store (all tree hashes)."
    )

    verifier_nodes: VerifierNodeStore = VerifierNodeStore()
    verifier_secrets: VerifierSecretStore = VerifierSecretStore()
    verifier_store_root(verifier_nodes, root, depth)
    print(
        "[Setup][Storage] Verifier saves root in node store; verifier secret store empty."
    )

    return prover_secrets, prover_nodes, root, verifier_nodes, verifier_secrets, depth


def test_paytree_standard_walkthrough() -> None:
    """Standard flow: prover sends full proof (leaf->root) for each payment."""
    print("\n")
    print("[Test][Standard] Start — full proof (leaf -> root) per payment")
    print()
    prover_secrets, prover_nodes, root, verifier_nodes, verifier_secrets, depth = (
        _run_standard_setup(NUM_LEAVES, LEAF_SECRETS)
    )
    auditor: AuditorState = AuditorState()
    auditor.receive_tree(root, depth)
    print(
        "[Auditor][Setup] Prover sends Merkle root to auditor (mocked). Auditor stores root."
    )
    print()

    prover_sent_indexes: ProverSentIndexStore = ProverSentIndexStore()
    verifier_received_indexes: VerifierReceivedIndexStore = VerifierReceivedIndexStore()

    last_proof: tuple[bytes, int, list[bytes]] | None = None
    for leaf_index in [0, 3, 4, 5, 6, 7]:
        print("[Standard][Leaf] ========== leaf_index =", leaf_index, "==========")
        print(
            "[Info] Prover previous sent payment indexes:",
            prover_sent_indexes.get_all(),
        )
        print(
            "[Info] Verifier previous received payment indexes:",
            verifier_received_indexes.get_all(),
        )
        print()

        # --- [Standard] Step 1 & 2: Prover reads leaf secret, builds full proof (leaf -> root) ---
        secret = prover_secrets[_leaf_index_to_binary(leaf_index, depth)]
        sibling_indexes = proof_indexes_standard(leaf_index, depth)
        siblings = _lookup_sibling_hashes(prover_nodes, sibling_indexes, depth)
        print("[Standard][Storage] Prover reads leaf secret from prover secret store.")
        print("[Info] Prover gets the secret for leaf", leaf_index, ":", secret)
        print()
        sibling_keys = get_sibling_keys_eytzinger(leaf_index, depth)
        print("[Info] Siblings until root (Eytzinger):", sibling_keys)
        print()
        print(
            "[Standard][Crypto] Prover builds full proof (leaf to root); prover gets sibling hashes from node store."
        )

        # --- [Standard] Step 3: Verifier reads sub-root (root) ---
        subroot_index = key_eytzinger(depth, 0, depth)
        subroot_node = verifier_nodes[subroot_index]
        print(
            "[Standard][Storage] Verifier reads sub-root (root) from verifier node store."
        )

        # --- [Standard] Step 4: Prover sends proof (secret + siblings) ---
        prover_sent_indexes.add(leaf_index)
        print("[Standard][Network] Prover sends secret and full siblings to verifier.")
        print("[Info] secret =", secret, "| siblings =", [x.hex() for x in siblings])

        # --- [Standard] Step 5: Verifier verifies proof ---
        verify_proof(secret, leaf_index, siblings, subroot_node, subroot_index, depth)
        print("[Standard][Crypto] Verifier verifies proof (leaf -> root).")

        # --- [Standard] Step 6: Verifier stores proof and secret after validation ---
        verifier_store_proof(verifier_nodes, leaf_index, siblings, depth)
        verifier_stores_secret(verifier_secrets, leaf_index, secret, depth)
        verifier_received_indexes.add(leaf_index)
        print(
            "[Standard][Storage] Verifier stores proof siblings, secret, and received index."
        )
        print()
        last_proof = (secret, leaf_index, siblings)

    # --- [Auditor] Verifier sends last leaf secret and proof to auditor ---
    assert last_proof is not None
    auditor.validate_proof(*last_proof)
    print(
        "[Auditor][Validate] Verifier sends last leaf secret and proof to auditor; "
        "auditor validates against known root."
    )
    print()


# ---------------------------------------------------------------------------
# Test: first optimization (pruned proof to sub-root)
# ---------------------------------------------------------------------------


def test_paytree_first_opt_walkthrough() -> None:
    """First-opt flow: prover sends pruned proof (leaf->sub-root) using LCA with prior payments."""
    print("\n")
    print("[Test][FirstOpt] Start — pruned proof (leaf -> sub-root) per payment")
    print()
    prover_secrets, prover_nodes, root, verifier_nodes, verifier_secrets, depth = (
        _run_standard_setup(NUM_LEAVES, LEAF_SECRETS)
    )
    auditor: AuditorState = AuditorState()
    auditor.receive_tree(root, depth)
    print(
        "[Auditor][Setup] Prover sends Merkle root to auditor (mocked). Auditor stores root."
    )
    print()

    prover_sent_indexes: ProverSentIndexStore = ProverSentIndexStore()
    verifier_received_indexes: VerifierReceivedIndexStore = VerifierReceivedIndexStore()

    last_proof: tuple[bytes, int, list[bytes]] | None = None
    for leaf_index in [0, 1, 3, 4, 6, 7]:
        print("[FirstOpt][Leaf] ========== leaf_index =", leaf_index, "==========")
        print(
            "[Info] Prover previous sent payment indexes:",
            prover_sent_indexes.get_all(),
        )
        print(
            "[Info] Verifier previous received payment indexes:",
            verifier_received_indexes.get_all(),
        )
        print()

        # --- [FirstOpt] Step 1 & 2: Prover reads leaf secret, computes sub-root (LCA with prior), builds pruned proof ---
        prior_leaves = verifier_received_indexes.get_all()
        secret = prover_secrets[_leaf_index_to_binary(leaf_index, depth)]
        pruned_indexes = proof_indexes_first_opt(leaf_index, prior_leaves, depth)
        pruned_siblings = _lookup_sibling_hashes(prover_nodes, pruned_indexes, depth)
        print("[FirstOpt][Storage] Prover reads leaf secret from prover secret store.")
        print("[Info] Prover gets the secret for leaf", leaf_index, ":", secret)
        print()
        sibling_keys_pruned = [
            _node_key(lev, pos, depth) for lev, pos in pruned_indexes
        ]
        print("[Info] Siblings (pruned) Eytzinger:", sibling_keys_pruned)
        print()
        print(
            "[FirstOpt][Crypto] Prover computes sub-root (LCA with prior); prover builds pruned proof (leaf -> sub-root)."
        )
        print(
            "[FirstOpt][Storage] Prover reads sibling hashes from prover node store for pruned path."
        )

        # --- [FirstOpt] Step 3: Prover sends pruned proof (secret + siblings) ---
        prover_sent_indexes.add(leaf_index)
        print(
            "[FirstOpt][Network] Prover sends secret and pruned siblings to verifier."
        )
        siblings_received = pruned_siblings
        print(
            "[Info] secret =",
            secret,
            "| siblings =",
            [x.hex() for x in siblings_received],
        )

        # --- [FirstOpt] Step 4: Verifier infers sub-root and reads it from store ---
        subroot_index = infer_subroot_index_for_incoming_pruned_merkle_proof(
            leaf_index, len(siblings_received), depth
        )
        subroot_node = verifier_nodes[subroot_index]
        print("[FirstOpt][Crypto] Verifier infers sub-root index from siblings count.")
        print(
            "[FirstOpt][Storage] Verifier reads sub-root node from verifier node store."
        )

        # --- [FirstOpt] Step 5: Verifier verifies proof ---
        verify_proof(
            secret,
            leaf_index,
            siblings_received,
            subroot_node,
            subroot_index,
            depth,
        )
        print("[FirstOpt][Crypto] Verifier verifies proof (leaf -> sub-root).")

        # --- [FirstOpt] Step 6: Verifier stores proof and secret after validation ---
        verifier_store_proof(verifier_nodes, leaf_index, siblings_received, depth)
        verifier_stores_secret(verifier_secrets, leaf_index, secret, depth)
        verifier_received_indexes.add(leaf_index)
        print(
            "[FirstOpt][Storage] Verifier stores proof siblings, secret, and received index."
        )
        print(
            "[Info] Verifier secrets (key -> hex):",
            {k: v.hex() for k, v in verifier_secrets.items()},
        )
        print("[Info] Verifier node store keys:", sorted(verifier_nodes.keys()))
        print()
        last_proof = (secret, leaf_index, siblings_received)

    # --- [FirstOpt][Auditor] Verifier rebuilds full proof for last leaf and sends to auditor ---
    assert last_proof is not None
    last_secret, last_leaf_index, _ = last_proof

    # Full proof (leaf -> root): use build_merkle_proof_indexes_for_leaf_a_given_ancestor_b
    full_sibling_indexes = build_merkle_proof_indexes_for_leaf_a_given_ancestor_b(
        0, last_leaf_index, depth, 0
    )
    dependency_indexes = get_proof_dependency_indexes(full_sibling_indexes, depth)

    node_hashes = batch_get_node_hashes_or_secrets(
        verifier_nodes, verifier_secrets, dependency_indexes, depth
    )
    full_siblings = [
        build_node_from_dependencies(lev, pos, node_hashes, depth)
        for lev, pos in full_sibling_indexes
    ]

    print(
        "[FirstOpt][Auditor] Verifier rebuilds full proof (leaf -> root) for last leaf "
        "from sparse node store and sends to auditor."
    )
    auditor.validate_proof(last_secret, last_leaf_index, full_siblings)
    print("[Auditor][Validate] Auditor validates full proof against known root.")
    print()


if __name__ == "__main__":
    test_paytree_standard_walkthrough()
    test_paytree_first_opt_walkthrough()
