FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
RUN mvn -B -DskipTests dependency:go-offline
COPY src ./src
RUN mvn -B -DskipTests package

FROM eclipse-temurin:21-jre
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 appuser
WORKDIR /app
COPY --from=build /build/target/api-gateway.jar /app/app.jar
USER appuser
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
