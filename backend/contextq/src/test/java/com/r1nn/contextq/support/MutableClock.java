package com.r1nn.contextq.support;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

/** Test clock that only moves when told to. Starts at 2026-11-18T00:00:00Z. */
public final class MutableClock extends Clock {

  private volatile Instant now;

  public MutableClock() {
    this(Instant.parse("2026-11-18T00:00:00Z"));
  }

  public MutableClock(Instant start) {
    this.now = start;
  }

  public void advance(Duration duration) {
    now = now.plus(duration);
  }

  public void set(Instant instant) {
    now = instant;
  }

  @Override
  public ZoneId getZone() {
    return ZoneOffset.UTC;
  }

  @Override
  public Clock withZone(ZoneId zone) {
    return this;
  }

  @Override
  public Instant instant() {
    return now;
  }
}
