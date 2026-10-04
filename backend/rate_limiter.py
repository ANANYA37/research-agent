"""Production-grade rate limiter for Groq API.

Implements:
- Token-bucket rate limiting for RPM and TPM
- Adaptive exponential backoff on 429 errors
- Request queue with concurrency control
- LLM response caching (semantic dedup)
- Automatic retry with jitter
"""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from langchain_core.messages import BaseMessage


# ---------------------------------------------------------------------------
# LLM Response Cache (in-memory, keyed by prompt hash)
# ---------------------------------------------------------------------------

class LLMCache:
    """Simple in-memory cache for LLM responses keyed on prompt content."""

    def __init__(self, max_entries: int = 200):
        self._store: dict[str, Any] = {}
        self._max = max_entries
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _hash(messages: list[BaseMessage]) -> str:
        raw = "||".join(m.content for m in messages)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, messages: list[BaseMessage]) -> Optional[Any]:
        key = self._hash(messages)
        result = self._store.get(key)
        if result is not None:
            self._hits += 1
        else:
            self._misses += 1
        return result

    def put(self, messages: list[BaseMessage], response: Any) -> None:
        key = self._hash(messages)
        # Simple eviction: drop oldest half when full
        if len(self._store) >= self._max:
            keys = list(self._store.keys())
            for k in keys[: len(keys) // 2]:
                del self._store[k]
        self._store[key] = response

    @property
    def stats(self) -> dict:
        return {"hits": self._hits, "misses": self._misses, "size": len(self._store)}


# ---------------------------------------------------------------------------
# Token Bucket Rate Limiter
# ---------------------------------------------------------------------------

@dataclass
class TokenBucket:
    """Token bucket for rate limiting (supports both RPM and TPM)."""

    capacity: float          # max tokens in the bucket
    refill_rate: float       # tokens added per second
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self):
        self.tokens = self.capacity
        self.last_refill = time.monotonic()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    async def acquire(self, count: float = 1.0):
        """Wait until `count` tokens are available, then consume them."""
        if count > self.capacity:
            raise ValueError('Request exceeds token bucket capacity; reduce the prompt size')
        while True:
            self._refill()
            if self.tokens >= count:
                self.tokens -= count
                return
            # How long until enough tokens are available?
            deficit = count - self.tokens
            wait = deficit / self.refill_rate
            await asyncio.sleep(wait)


# ---------------------------------------------------------------------------
# Groq Rate-Limited LLM Wrapper
# ---------------------------------------------------------------------------

class GroqRateLimiter:
    """
    Wraps a ChatGroq instance with production-grade rate limiting.

    Configurable for both Free Tier and Developer Tier limits:
    - Free:     ~30 RPM, ~6000 TPM
    - Dev:      ~300 RPM, ~60000 TPM
    """

    def __init__(
        self,
        llm,
        rpm: int = 28,           # stay slightly under the limit
        tpm: int = 5500,         # stay slightly under the limit
        max_concurrent: int = 2, # max parallel LLM calls
        max_retries: int = 5,
        base_delay: float = 2.0,
        enable_cache: bool = True,
    ):
        self.llm = llm
        self.max_retries = max_retries
        self.base_delay = base_delay

        # Token buckets — refill rate = limit / 60 (per second)
        self._rpm_bucket = TokenBucket(capacity=rpm, refill_rate=rpm / 60.0)
        self._tpm_bucket = TokenBucket(capacity=tpm, refill_rate=tpm / 60.0)

        # Concurrency semaphore — prevents bursting many calls at once
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # Cache
        self._cache = LLMCache() if enable_cache else None

        # Adaptive backoff state
        self._consecutive_429s = 0
        self._global_cooldown_until = 0.0

    def _estimate_tokens(self, messages: list[BaseMessage]) -> int:
        """Rough token estimate: ~4 chars per token (conservative)."""
        total_chars = sum(len(m.content) for m in messages)
        return max(total_chars // 3, 50)  # conservative: 3 chars/token

    async def ainvoke(self, messages: list[BaseMessage], **kwargs) -> Any:
        """Rate-limited, cached, retrying wrapper around llm.ainvoke()."""

        # 1. Check cache first
        if self._cache:
            cached = self._cache.get(messages)
            if cached is not None:
                print(f"  [Cache HIT] Skipping Groq call ({self._cache.stats})")
                return cached

        estimated_tokens = self._estimate_tokens(messages)

        # 2. Acquire semaphore (concurrency limit)
        async with self._semaphore:
            # 3. Wait for global cooldown (adaptive backoff)
            now = time.monotonic()
            if now < self._global_cooldown_until:
                wait = self._global_cooldown_until - now
                print(f"  [Rate Limiter] Global cooldown: waiting {wait:.1f}s")
                await asyncio.sleep(wait)

            # 4. Acquire RPM token
            await self._rpm_bucket.acquire(1)

            # 5. Acquire TPM tokens
            await self._tpm_bucket.acquire(estimated_tokens)

            # 6. Call with retry + exponential backoff
            last_error = None
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = await self.llm.ainvoke(messages, **kwargs)

                    # Reset backoff on success
                    self._consecutive_429s = 0

                    # Cache the result
                    if self._cache:
                        self._cache.put(messages, response)

                    return response

                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()

                    is_rate_limit = (
                        "429" in error_str
                        or "rate" in error_str
                        or "too many" in error_str
                        or "quota" in error_str
                        or "limit" in error_str
                    )

                    if is_rate_limit:
                        self._consecutive_429s += 1

                        # Exponential backoff with jitter
                        import random
                        delay = self.base_delay * (2 ** (attempt - 1))
                        jitter = random.uniform(0, delay * 0.3)
                        total_delay = delay + jitter

                        # Adaptive: after repeated 429s, increase global cooldown
                        if self._consecutive_429s >= 3:
                            cooldown = min(60.0, 10.0 * self._consecutive_429s)
                            self._global_cooldown_until = time.monotonic() + cooldown
                            print(
                                f"  [Rate Limiter] Repeated 429s — global cooldown {cooldown:.0f}s"
                            )

                        print(
                            f"  [Rate Limiter] 429 on attempt {attempt}/{self.max_retries}. "
                            f"Waiting {total_delay:.1f}s (consecutive 429s: {self._consecutive_429s})"
                        )
                        await asyncio.sleep(total_delay)

                    elif attempt < self.max_retries:
                        # Non-rate-limit error — short retry
                        await asyncio.sleep(1.0)
                        print(
                            f"  [Rate Limiter] Non-429 error on attempt {attempt}: {e}"
                        )
                    else:
                        raise

            raise last_error  # type: ignore[misc]

    @property
    def cache_stats(self) -> dict:
        if self._cache:
            return self._cache.stats
        return {"hits": 0, "misses": 0, "size": 0}
