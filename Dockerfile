FROM python:3.12-slim
LABEL io.modelcontextprotocol.server.name="io.github.CYAN-ECLIPSE-TECHNOLOGIES-LLC/license-server"
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .  && useradd -r appuser  && mkdir -p /app/runtime  && chown appuser:appuser /app/runtime
ENV CETLIC_RUNTIME_DIR=/app/runtime
USER appuser
ENTRYPOINT ["python", "-m", "license_server"]
