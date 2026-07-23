"""Token bucket behavior."""

from app.sender import TokenBucket


def test_bucket_allows_burst_up_to_capacity():
    bucket = TokenBucket(rate_per_second=5)
    grants = sum(1 for _ in range(10) if bucket.try_acquire())
    assert grants == 5


def test_bucket_refills_over_time(monkeypatch):
    import app.sender as sender_mod

    clock = {"t": 0.0}
    monkeypatch.setattr(sender_mod.time_mod, "monotonic", lambda: clock["t"])

    bucket = TokenBucket(rate_per_second=2)
    assert bucket.try_acquire()
    assert bucket.try_acquire()
    assert not bucket.try_acquire()

    clock["t"] += 1.0
    assert bucket.try_acquire()
    assert bucket.try_acquire()
    assert not bucket.try_acquire()
