package com.r1nn.contextq.support;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

/**
 * Replaces the application clock with a {@link MutableClock} that tests move by hand. One bean
 * serves both {@code Clock} and {@code MutableClock} injection points.
 */
@TestConfiguration(proxyBeanMethods = false)
public class FixedClockConfiguration {

  @Bean
  @Primary
  MutableClock mutableClock() {
    return new MutableClock(Instant.now().truncatedTo(ChronoUnit.SECONDS)); // DB keeps microseconds
  }
}
