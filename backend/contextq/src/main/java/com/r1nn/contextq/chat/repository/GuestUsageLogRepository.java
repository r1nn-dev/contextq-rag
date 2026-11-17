package com.r1nn.contextq.chat.repository;

import com.r1nn.contextq.chat.domain.GuestUsageLog;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface GuestUsageLogRepository extends JpaRepository<GuestUsageLog, Long> {

  List<GuestUsageLog> findBySidHash(String sidHash);
}
