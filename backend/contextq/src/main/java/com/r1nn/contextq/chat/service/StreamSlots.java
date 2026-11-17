package com.r1nn.contextq.chat.service;

import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

/**
 * Open streams per user or guest session, counted in memory (policy §8.1 동시 스트림, api-spec §0.7). A
 * slot is taken before ai-server is called and returned exactly once when the stream ends, whatever
 * the path (done, error, client cancel, pre-stream failure).
 */
@Component
public class StreamSlots {

  private final Map<String, Integer> open = new ConcurrentHashMap<>();

  /** A held slot; {@link #release()} is idempotent. */
  public final class Slot {
    private final String key;
    private final AtomicBoolean held = new AtomicBoolean(true);

    private Slot(String key) {
      this.key = key;
    }

    public void release() {
      if (held.compareAndSet(true, false)) {
        open.computeIfPresent(key, (k, count) -> count <= 1 ? null : count - 1);
      }
    }
  }

  /**
   * @param key {@code u:<userId>} or {@code g:<sidHash>}
   * @throws BusinessException {@code CONCURRENT_STREAM_LIMIT} when {@code limit} streams are open
   */
  public Slot acquire(String key, int limit) {
    boolean[] granted = {false};
    open.compute(
        key,
        (k, count) -> {
          int current = count == null ? 0 : count;
          if (current >= limit) {
            return count;
          }
          granted[0] = true;
          return current + 1;
        });
    if (!granted[0]) {
      throw new BusinessException(ErrorCode.CONCURRENT_STREAM_LIMIT);
    }
    return new Slot(key);
  }

  /** Open streams for a key (monitoring and tests). */
  public int openCount(String key) {
    return open.getOrDefault(key, 0);
  }
}
