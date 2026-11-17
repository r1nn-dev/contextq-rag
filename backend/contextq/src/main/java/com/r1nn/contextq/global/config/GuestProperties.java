package com.r1nn.contextq.global.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * Guest limits that operations may change (policy §8.1).
 *
 * @param sessionsPerIpPerHour new guest sessions per IP per hour (30; 60 on the exhibition day)
 */
@ConfigurationProperties("chat.guest")
public record GuestProperties(@DefaultValue("30") int sessionsPerIpPerHour) {}
