# stage 1: build
FROM gradle:8-jdk21 AS build

WORKDIR /app

# copy dependency files first to cache the dependency layer
# source changes will not trigger re-download of dependencies
COPY build.gradle settings.gradle ./
COPY gradle/ gradle/
RUN gradle dependencies --no-daemon || true

COPY src/ src/
RUN gradle bootJar --no-daemon -x test  # -x test: tests run separately in CI

# stage 2: runtime (JRE only; alpine for minimal image size)
FROM eclipse-temurin:21-jre-alpine AS runtime

WORKDIR /app

COPY --from=build /app/build/libs/*.jar app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "app.jar"]