# =============================================================================
# Documentation Dockerfile — HSBC Standard Build (Starlight / AstroJS)
#
# Replaces the former MkDocs-based image per ADR-141. Pure Node toolchain.
# Listens on port 3000 to match the Helm chart's containerPort and
# liveness/readiness probe configuration. The Astro prebuild hook
# (tools/build-notebooks.mjs) walks ../../docs/notebooks and
# ../../tests/e2e/notebooks relative to the package root, so the
# repo-split stages those trees at the expected relative position.
#
# No Python, no nbconvert, no Pandoc. Notebooks are nbstripout'd so the
# converter only needs to handle markdown + code cells, not outputs.
# =============================================================================

FROM nexus3.systems.uk.hsbc:18096/com/hsbc/group/itid/es/dc/ubuntu/gcr-ubuntu-2404:latest AS build

ARG APP_HOME=/app
ARG ALM_NEXUS302_TOKEN_USERNAME
ARG ALM_NEXUS302_TOKEN_PASSWORD
ENV TZ=Etc/UTC

LABEL noSecretInContainerImageMetadata="confirmed"
ARG DEBIAN_FRONTEND=noninteractive

RUN ln -snf "/usr/share/zoneinfo/$TZ" /etc/localtime && echo "$TZ" > /etc/timezone

# --- Certificates + private APT mirror ---
COPY build/hsbc_root.cer /etc/apt/hsbc_root.cer
COPY build/truststore.pem /etc/apt/truststore.pem
RUN rm -rf /etc/apt/sources.list.d/*

RUN echo "deb [trusted=yes] https://${ALM_NEXUS302_TOKEN_USERNAME}:${ALM_NEXUS302_TOKEN_PASSWORD}@nexus302.systems.uk.hsbc:8081/nexus/repository/apt-proxy-ubuntu-n3p_q/ubuntu/ noble main universe" > /etc/apt/sources.list \
 && echo "deb [trusted=yes] https://${ALM_NEXUS302_TOKEN_USERNAME}:${ALM_NEXUS302_TOKEN_PASSWORD}@nexus302.systems.uk.hsbc:8081/nexus/repository/apt-proxy-ubuntu-n3p_q/ubuntu/ noble-updates main universe" >> /etc/apt/sources.list \
 && echo "deb [trusted=yes] https://${ALM_NEXUS302_TOKEN_USERNAME}:${ALM_NEXUS302_TOKEN_PASSWORD}@nexus302.systems.uk.hsbc:8081/nexus/repository/apt-proxy-ubuntu-n3p_q/ubuntu/ noble-security main universe" >> /etc/apt/sources.list \
 && apt-get update \
 && apt-get install -yq --no-install-recommends curl ca-certificates gnupg \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* /tmp/*

# --- Node.js 22.x from NodeSource via HSBC Nexus proxy ---
# Node 22 required — Astro 6 enforces engines.node >=22.12.0 at runtime
# and refuses to build on Node 20. HSBC Jenkins agents are native
# linux/amd64 (no qemu emulation), so Node 22 runs cleanly here.
# If HSBC publishes Node via a Nexus npm-proxy the ENV NPM_CONFIG_REGISTRY
# directive below wires it up. Adjust the nodesource APT repo URL if
# HSBC mirrors nodesource separately.
RUN curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
    | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
 && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
    > /etc/apt/sources.list.d/nodesource.list \
 && apt-get update \
 && apt-get install -yq --no-install-recommends nodejs \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Configure npm to use HSBC Nexus npm proxy if configured in the ecosystem.
# The default below falls back to public npm over the HSBC TLS trust store.
ENV NPM_CONFIG_CAFILE=/etc/apt/truststore.pem
ENV NPM_CONFIG_UPDATE_NOTIFIER=false
ENV NPM_CONFIG_FUND=false
ENV NPM_CONFIG_AUDIT=false

# --- Build ---
WORKDIR ${APP_HOME}

# Install dependencies first for layer caching
COPY package.json package-lock.json ./
RUN npm ci

# Copy package source + notebook source trees at their expected relative
# positions (the prebuild script walks ../../docs/notebooks and
# ../../tests/e2e/notebooks relative to the package root).
COPY . ./

# Skip offline-postbuild scripts — the deployed container serves from HTTP
# where absolute paths and fetch work fine. Offline scripts are only for
# the double-click-dist workflow.
ENV SKIP_OFFLINE_POSTBUILD=1

# Skip the Starlight prebuild pipeline (ADR-142): repo-split has already
# regenerated src/content/docs/ and src/content/docs/notebooks/ from the
# upstream docs/ tree and baked them into this split repo. The HSBC build
# context does not include docs/ or tools/repo-split/build-handover.sh,
# so running the prebuild inside the container would fail.
ENV SKIP_PREBUILD=1

RUN npm run build

# --- Runtime stage: minimal nginx image serving the static dist/ ---
FROM nexus3.systems.uk.hsbc:18096/com/hsbc/group/itid/es/dc/ubuntu/gcr-ubuntu-2404:latest AS runtime

ARG APP_HOME=/app
ARG ALM_NEXUS302_TOKEN_USERNAME
ARG ALM_NEXUS302_TOKEN_PASSWORD
ENV TZ=Etc/UTC

LABEL noSecretInContainerImageMetadata="confirmed"
ARG DEBIAN_FRONTEND=noninteractive

RUN ln -snf "/usr/share/zoneinfo/$TZ" /etc/localtime && echo "$TZ" > /etc/timezone

COPY build/hsbc_root.cer /etc/apt/hsbc_root.cer
COPY build/truststore.pem /etc/apt/truststore.pem
RUN rm -rf /etc/apt/sources.list.d/*

RUN echo "deb [trusted=yes] https://${ALM_NEXUS302_TOKEN_USERNAME}:${ALM_NEXUS302_TOKEN_PASSWORD}@nexus302.systems.uk.hsbc:8081/nexus/repository/apt-proxy-ubuntu-n3p_q/ubuntu/ noble main universe" > /etc/apt/sources.list \
 && echo "deb [trusted=yes] https://${ALM_NEXUS302_TOKEN_USERNAME}:${ALM_NEXUS302_TOKEN_PASSWORD}@nexus302.systems.uk.hsbc:8081/nexus/repository/apt-proxy-ubuntu-n3p_q/ubuntu/ noble-updates main universe" >> /etc/apt/sources.list \
 && echo "deb [trusted=yes] https://${ALM_NEXUS302_TOKEN_USERNAME}:${ALM_NEXUS302_TOKEN_PASSWORD}@nexus302.systems.uk.hsbc:8081/nexus/repository/apt-proxy-ubuntu-n3p_q/ubuntu/ noble-security main universe" >> /etc/apt/sources.list \
 && apt-get update \
 && apt-get install -yq --no-install-recommends nginx curl \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* /tmp/*

# Copy built static site from the build stage
COPY --from=build ${APP_HOME}/dist /var/www/docs

# nginx site config — port 3000, directory-style URLs plus .html fallback
RUN printf 'server {\n\
    listen 3000;\n\
    root /var/www/docs;\n\
    index index.html;\n\
    location / { try_files $uri $uri/ $uri.html =404; }\n\
    location ~* \\.(css|js|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {\n\
        expires 1y;\n\
        add_header Cache-Control "public, immutable";\n\
    }\n\
    error_page 404 /404.html;\n\
}\n' > /etc/nginx/sites-available/docs \
 && ln -sf /etc/nginx/sites-available/docs /etc/nginx/sites-enabled/docs \
 && rm -f /etc/nginx/sites-enabled/default

# Create non-root user (matches the Helm chart's expected uid 1009 → 'glh')
RUN useradd -ms /bin/bash -d /home/glh -u 1009 glh \
 && mkdir -p /var/log/nginx /var/lib/nginx /var/run \
 && chown -R glh:glh /var/log/nginx /var/lib/nginx /var/run /var/www/docs \
 && chmod -R 755 /var/www/docs

USER glh
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:3000/ || exit 1

# Serve pre-built static HTML — no conversion at startup, minimal RAM
ENTRYPOINT ["nginx", "-g", "daemon off;"]
