package com.r1nn.contextq.chat.service;

import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.global.config.QuotaProperties;
import java.time.Clock;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

/**
 * Per-user questions per minute as an in-memory token bucket (policy §8.1, api-spec §0.7).
 *
 * <p>Capacity {@code perMinute}, refilled continuously ({@code perMinute} tokens per 60 s). The
 * bucket is lost on restart, which the policy accepts (single instance, no Redis).
 */
@Component
public class QuestionRateLimiter {

  private static final long WINDOW_NANOS = Duration.ofMinutes(1).toNanos();

  private final Map<Long, Bucket> buckets = new ConcurrentHashMap<>();
  private final QuotaProperties properties;
  private final Clock clock;

  public QuestionRateLimiter(QuotaProperties properties, Clock clock) {
    this.properties = properties;
    this.clock = clock;
  }

  /**
   * Takes one token for the user.
   *
   * @throws BusinessException {@code RATE_LIMITED} with {@code Retry-After} (seconds until the next
   *     token, rounded up)
   */
  public void acquire(Long userId) {
    long now = nowNanos();
    Bucket bucket = buckets.computeIfAbsent(userId, id -> new Bucket(properties.perMinute(), now));
    long waitNanos = bucket.tryTake(properties.perMinute(), now);
    if (waitNanos > 0) {
      long seconds = (waitNanos + 999_999_999L) / 1_000_000_000L;
      throw BusinessException.retryAfter(ErrorCode.RATE_LIMITED, seconds);
    }
  }

  private long nowNanos() {
    var instant = clock.instant();
    return instant.getEpochSecond() * 1_000_000_000L + instant.getNano();
  }

  /** Token bucket with continuous refill; tokens are stored as fractions via nanos. */
  private static final class Bucket {
    private double tokens;
    private long updatedNanos;

    Bucket(int capacity, long now) {
      this.tokens = capacity;
      this.updatedNanos = now;
    }

    /**
     * @return 0 when a token was taken, otherwise nanos until one token is available
     */
    synchronized long tryTake(int capacity, long now) {
      double refill = (double) (now - updatedNanos) * capacity / WINDOW_NANOS;
      tokens = Math.min(capacity, tokens + Math.max(0, refill));
      updatedNanos = now;
      if (tokens >= 1) {
        tokens -= 1;
        return 0;
      }
      double missing = 1 - tokens;
      return (long) Math.ceil(missing * WINDOW_NANOS / capacity);
    }
  }
}
