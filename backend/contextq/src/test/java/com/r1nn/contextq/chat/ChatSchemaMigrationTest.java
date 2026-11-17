package com.r1nn.contextq.chat;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.r1nn.contextq.TestcontainersConfiguration;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

/** V2 migration matches db-design §3.1·§3.6~§3.8 (tables, constraints, indexes). */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@Transactional
class ChatSchemaMigrationTest {

  @Autowired private JdbcTemplate jdbc;

  @Test
  void createsTablesInAppSchema() {
    List<String> tables =
        jdbc.queryForList(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'app'",
            String.class);

    assertThat(tables).contains("users", "conversations", "messages", "message_sources");
  }

  @Test
  void createsDocumentedIndexes() {
    List<String> indexes =
        jdbc.queryForList(
            "SELECT indexname FROM pg_indexes WHERE schemaname = 'app'", String.class);

    assertThat(indexes)
        .contains(
            "idx_users_status_locked",
            "idx_conv_user_updated",
            "idx_msg_conv_created",
            "idx_msg_conv_role_status",
            "idx_msg_user_quota",
            "idx_ms_message_id");
  }

  @Test
  void singleConversationRequiresSourceKey() {
    long userId = insertUser("schema-single@example.com");

    assertThatThrownBy(() -> insertConversation(userId, "SINGLE", null, null, null))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining("chk_conv_mode_source");
  }

  @Test
  void compareConversationRejectsSingleSourceKey() {
    long userId = insertUser("schema-compare@example.com");

    assertThatThrownBy(() -> insertConversation(userId, "COMPARE", "langchain_v03", "a", "b"))
        .isInstanceOf(DataIntegrityViolationException.class);
  }

  @Test
  void compareConversationAcceptsBothSides() {
    long userId = insertUser("schema-compare-ok@example.com");

    insertConversation(userId, "COMPARE", null, "langchain_v03", "langchain_v1x");
  }

  @Test
  void duplicateEmailIsRejected() {
    insertUser("dup@example.com");

    assertThatThrownBy(() -> insertUser("dup@example.com"))
        .isInstanceOf(DataIntegrityViolationException.class);
  }

  @Test
  void failedCountAboveFiveIsRejected() {
    assertThatThrownBy(
            () ->
                jdbc.update(
                    "INSERT INTO users (email, password_hash, role, status, login_failed_count,"
                        + " created_at, updated_at) VALUES ('x@example.com', 'h', 'ROLE_USER',"
                        + " 'ACTIVE', 6, now(), now())"))
        .isInstanceOf(DataIntegrityViolationException.class);
  }

  private long insertUser(String email) {
    return jdbc.queryForObject(
        "INSERT INTO users (email, password_hash, role, status, login_failed_count, created_at,"
            + " updated_at) VALUES (?, 'hash', 'ROLE_USER', 'ACTIVE', 0, now(), now())"
            + " RETURNING id",
        Long.class,
        email);
  }

  private void insertConversation(
      long userId, String mode, String sourceKey, String sourceKeyA, String sourceKeyB) {
    jdbc.update(
        "INSERT INTO conversations (user_id, title, mode, source_key, source_key_a, source_key_b,"
            + " message_count, created_at, updated_at) VALUES (?, 't', ?, ?, ?, ?, 0, now(),"
            + " now())",
        userId,
        mode,
        sourceKey,
        sourceKeyA,
        sourceKeyB);
  }
}
