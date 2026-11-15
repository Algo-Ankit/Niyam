from niyam.retrieval.store import fuse


def test_fuse_rewards_items_ranked_by_both_lists() -> None:
    fused = fuse([["a", "b", "c"], ["c", "a", "d"]])
    assert [item for item, _ in fused] == ["a", "c", "b", "d"]
    assert fused[0][1] == 1 / 61 + 1 / 62


def test_fuse_of_nothing_is_empty() -> None:
    assert fuse([[], []]) == []
