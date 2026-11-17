package com.r1nn.contextq;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;
import org.testcontainers.utility.MountableFile;

@TestConfiguration(proxyBeanMethods = false)
public class TestcontainersConfiguration {

  // same image as infra/docker-compose.yml so the test DB starts from the local initial state
  private static final String POSTGRES_IMAGE = "postgres:16-alpine";

  // relative to backend/contextq (Gradle test working directory)
  private static final String INIT_SQL = "../../infra/postgres/init.sql";

  @Bean
  @ServiceConnection
  PostgreSQLContainer postgresContainer() {
    return new PostgreSQLContainer(DockerImageName.parse(POSTGRES_IMAGE))
        .withCopyFileToContainer(
            MountableFile.forHostPath(INIT_SQL), "/docker-entrypoint-initdb.d/init.sql");
  }
}
