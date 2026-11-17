package com.r1nn.contextq.chat.service;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

/**
 * Answers whose terminal UPDATE failed twice (policy §2.3 "스트림 완료 후 DB 저장 실패").
 *
 * <p>Kept in memory because the database just failed; the sweeper later stores them as {@code
 * FAILED(PERSIST_ERROR)} with the text the browser already received. Lost on restart — those rows
 * then end as {@code STALE}.
 */
@Component
public class PersistFailureRegistry {

  private final Map<Long, String> contents = new ConcurrentHashMap<>();

  void record(Long answerId, String content) {
    contents.put(answerId, content == null ? "" : content);
  }

  /** Removes and returns the received text when the answer was recorded. */
  Optional<String> consume(Long answerId) {
    return Optional.ofNullable(contents.remove(answerId));
  }
}
