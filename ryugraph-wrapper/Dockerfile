# Ryugraph Wrapper Dockerfile
# HSBC Standard Build

FROM nexus3.systems.uk.hsbc:18096/com/hsbc/group/itid/es/dc/ubuntu/gcr-ubuntu-2404:latest

ARG APP_HOME=/app
ARG ALM_NEXUS302_TOKEN_USERNAME
ARG ALM_NEXUS302_TOKEN_PASSWORD
ARG RYUGRAPH_VERSION=25.9.2
ENV TZ=Etc/UTC

LABEL noSecretInContainerImageMetadata="confirmed"
ARG DEBIAN_FRONTEND=noninteractive

RUN ln -snf "/usr/share/zoneinfo/$TZ" /etc/localtime && echo "$TZ" > /etc/timezone

ENV APP_HOME /app

# Use Python 3.12 from HSBC base image
ENV PATH="/app/venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy certificates and set up APT sources for private repository
COPY build/hsbc_root.cer /etc/apt/hsbc_root.cer
COPY build/truststore.pem /etc/apt/truststore.pem
RUN rm -rf  /etc/apt/sources.list.d/*

RUN echo "deb [trusted=yes] https://${ALM_NEXUS302_TOKEN_USERNAME}:${ALM_NEXUS302_TOKEN_PASSWORD}@nexus302.systems.uk.hsbc:8081/nexus/repository/apt-proxy-ubuntu-n3p_g/ubuntu/ noble main universe" > /etc/apt/sources.list \
&& echo "deb [trusted=yes] https://${ALM_NEXUS302_TOKEN_USERNAME}:${ALM_NEXUS302_TOKEN_PASSWORD}@nexus302.systems.uk.hsbc:8081/nexus/repository/apt-proxy-ubuntu-n3p_g/ubuntu/ noble-updates main universe" >> /etc/apt/sources.list \
&& echo "deb [trusted=yes] https://${ALM_NEXUS302_TOKEN_USERNAME}:${ALM_NEXUS302_TOKEN_PASSWORD}@nexus302.systems.uk.hsbc:8081/nexus/repository/apt-proxy-ubuntu-n3p_g/ubuntu/ noble-security main universe" >> /etc/apt/sources.list \
&& apt-get update \
&& apt-get install -yq --no-install-recommends \
gcc g++ make curl python3-pip python3.12 python3.12-venv python3.12-dev \
&& apt-get clean \
&& rm -rf /var/lib/apt/lists/* /tmp/*

# Configure pip to use the private repository
RUN mkdir -p /root/.config/pip/ \
&& cat /etc/apt/hsbc_root.cer >> /root/.config/pip/truststore.pem \
&& echo "[global]\n\
trusted-host=nexus302.systems.uk.hsbc:8081\n\
index-url = https://${ALM_NEXUS302_TOKEN_USERNAME}:${ALM_NEXUS302_TOKEN_PASSWORD}@nexus302.systems.uk.hsbc:8081/nexus/repository/pypi-group/simple\n\
extra-index-url = https://${ALM_NEXUS302_TOKEN_USERNAME}:${ALM_NEXUS302_TOKEN_PASSWORD}@nexus302.systems.uk.hsbc:8081/nexus/repository/pypi-proxy_n3p/simple https://${ALM_NEXUS302_TOKEN_USERNAME}:${ALM_NEXUS302_TOKEN_PASSWORD}@nexus302.systems.uk.hsbc:8081/nexus/repository/pypi-hosted_n3-prd/simple https://${ALM_NEXUS302_TOKEN_USERNAME}:${ALM_NEXUS302_TOKEN_PASSWORD}@nexus302.systems.uk.hsbc:8081/nexus/repository/pypi-hosted-iHub-dev-n3p/simple\n\
cert = /root/.config/pip/truststore.pem" > /etc/pip.conf

# Create a virtual environment using Python 3.12
RUN python3.12 -m venv /app/venv

# Copy project files
WORKDIR ${APP_HOME}
COPY requirements.txt ./
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install dependencies
RUN . /app/venv/bin/activate && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir certifi && \
    pip install --no-cache-dir PyJWT && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --no-deps . && \
    rm -f /app/venv/bin/ryugraph.so

# Create non-root user
RUN useradd -ms /bin/bash -d /home/glh -u 1009 glh \
    && cp /etc/skel/.bashrc ${APP_HOME} \
    && cp /etc/skel/.profile ${APP_HOME}/.bash_profile \
    && CERT_FILE=$(${APP_HOME}/venv/bin/python -c "import certifi; print(certifi.where())") \
    && cat /etc/apt/truststore.pem >> "$CERT_FILE" \
    && chown glh:glh /etc/pip.conf && chmod 644 /etc/pip.conf \
    && chmod -R 755 ${APP_HOME}/ \
    && chown -R glh:glh ${APP_HOME}/

# Bake algo extension binary into image (ADR-138).
# The wrapper runs `LOAD algo` at startup; Ryugraph resolves the extension
# cache at $HOME/.ryu/extension/<native-lib-version>/linux_amd64/algo/,
# where $HOME is /home/glh because the container runs as user `glh` below.
#
# The path uses 25.9.0 — that's Ryugraph's *native library* build version,
# hardcoded in its extension loader. It is NOT the Python wheel version
# (which resolves to 25.9.2 from PyPI). Mismatching the two causes
# `LOAD algo` to silently fail at pod startup and every /algo/* endpoint
# to return "function page_rank is not defined". When Ryugraph bumps its
# native library version, update this path AND the source path in
# tools/repo-split/refresh-algo-extension.sh, then re-run that script.
#
# The binary is pre-vendored in the monorepo at
# tools/repo-split/vendor/libalgo.ryu_extension (443 KB, committed to git)
# and copied into this handoff at vendor/libalgo.ryu_extension by
# build-repos.sh. HSBC Jenkins/Airflow hosts have no ghcr.io egress, so the
# binary must be self-contained in the handoff — no docker pull at build
# time. See ADR-138.
RUN mkdir -p /home/glh/.ryu/extension/25.9.0/linux_amd64/algo \
    && chown -R glh:glh /home/glh/.ryu
COPY --chown=glh:glh vendor/libalgo.ryu_extension \
    /home/glh/.ryu/extension/25.9.0/linux_amd64/algo/libalgo.ryu_extension

USER glh
WORKDIR ${APP_HOME}

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

ENV WRAPPER_INSTANCE_ID="" \
    WRAPPER_SNAPSHOT_ID="" \
    WRAPPER_MAPPING_ID="" \
    WRAPPER_OWNER_ID="" \
    WRAPPER_OWNER_USERNAME="unknown" \
    WRAPPER_CONTROL_PLANE_URL="http://localhost" \
    WRAPPER_GCS_BASE_PATH="gs://placeholder" \
    WRAPPER_DEV_SKIP_STARTUP="1" \
    LOG_LEVEL=INFO \
    LOG_FORMAT=json

ENTRYPOINT ["/app/venv/bin/python", "-m", "uvicorn", "wrapper.main:app", "--host", "0.0.0.0", "--port", "8000"]
