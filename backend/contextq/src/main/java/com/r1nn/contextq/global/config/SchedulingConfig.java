package com.r1nn.contextq.global.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/** Enables {@code @Scheduled} batch jobs (stuck answer sweeper, token cleanup). */
@Configuration
@EnableScheduling
public class SchedulingConfig {}
