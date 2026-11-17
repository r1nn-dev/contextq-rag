package com.r1nn.contextq.global.config;

import static org.assertj.core.api.Assertions.assertThat;

import com.r1nn.contextq.TestcontainersConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

@Import(TestcontainersConfiguration.class)
@SpringBootTest
class DatabaseConnectionTest {

  @Autowired private JdbcTemplate jdbcTemplate;

  @Test
  void connectionUsesAppSearchPath() {
    assertThat(jdbcTemplate.queryForObject("SHOW search_path", String.class)).isEqualTo("app");
  }

  @Test
  void connectionUsesSeoulTimeZone() {
    assertThat(jdbcTemplate.queryForObject("SHOW TimeZone", String.class)).isEqualTo("Asia/Seoul");
  }

  @Test
  void flywayHistoryLivesInAppSchema() {
    Integer count =
        jdbcTemplate.queryForObject(
            "SELECT count(*) FROM information_schema.tables"
                + " WHERE table_schema = 'app' AND table_name = 'flyway_schema_history'",
            Integer.class);
    assertThat(count).isEqualTo(1);
  }
}
