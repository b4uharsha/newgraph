---
title: "ADR-138: Bake Algo Extension Into Wrapper Image"
---

| | |
|---|---|
| **Date** | 2026-04-09 |
| **Status** | Accepted |
| **Category** | infrastructure |


## Context

The Ryugraph native graph algorithms (`page_rank`, `wcc`, `scc`, `louvain`, `kcore`) live in the
`algo` extension. Until now, the `ryugraph-wrapper` loaded that extension at startup by talking
to a separate `extension-server` Kubernetes pod (image
`ghcr.io/predictable-labs/extension-repo:latest`) that served the binary over HTTP:

```python
# packages/ryugraph-wrapper/src/wrapper/services/database.py - old flow
extension_server_url = os.environ.get("RYUGRAPH_EXTENSION_SERVER_URL")
if extension_server_url:
    self._connection.execute(f"INSTALL algo FROM '{extension_server_url}/'")
    self._connection.execute("LOAD algo")
```

This worked in our own GKE London cluster, but it had two real problems:

### 1. HSBC cannot run the extension-server pod

HSBC's on-prem Kubernetes cluster does **not** run `extension-server`, and HSBC has been clear
they do not intend to add another upstream image to their environment. Without the pod, every
call to `/algo/pagerank`, `/algo/wcc`, `/algo/louvain`, `/algo/kcore`, or `/algo/scc` failed at
the wrapper with:

```
Catalog exception: function page_rank is not defined. This function exists in the ALGO extension.
You can install and load the extension by running 'INSTALL ALGO; LOAD EXTENSION ALGO;'
```

There was no HSBC-side fix. Either we ship the binary inside the wrapper, or HSBC loses native
graph algorithms entirely and has to fall back to in-process NetworkX (which is materially
slower for large graphs).

### 2. Even in GKE London, the runtime install was fragile

The wrapper's `_init_database()` retried `INSTALL algo FROM '<url>'` with linear backoff
(1s, 2s, 3s — up to ~6s of total retry time). That retry window existed because the wrapper
pod and the `extension-server` pod start independently, and the wrapper would occasionally lose
the race. This created an entire class of "is extension-server ready yet?" incidents that had
nothing to do with the actual workload — they were just startup ordering flakiness.

### What we already knew

ADR-026 ("ARM64 Algo Extension Workaround") established that the upstream `linux_arm64`
directory inside `ghcr.io/predictable-labs/extension-repo:latest` actually contains x86-64 ELF
binaries, so wrapper containers must be built `--platform=linux/amd64` regardless of where they
run. That platform constraint is independent of *how* the binary is delivered to the wrapper,
and it still applies after this ADR.

---

## Decision

Bake the `algo` extension binary directly into the `ryugraph-wrapper` Docker image at build
time, at the exact path Ryugraph looks for cached extensions. At runtime the wrapper simply
calls `LOAD algo` — no HTTP install, no `RYUGRAPH_EXTENSION_SERVER_URL`, no `extension-server`
pod anywhere.

### Build-time: lift the binary out of the upstream image via an Earthly artifact target

Earthly does **not** support `COPY --from=<external-image>` the way Docker does; attempting it
fails the build with:

```
Earthfile:… COPY --from not implemented. Use COPY artifacts form instead
```

The canonical Earthly pattern for lifting files out of an arbitrary registry image is to wrap
that image in a named target that uses `FROM + SAVE ARTIFACT`, then reference the artifact via
`+target/artifact` from the destination stage.

`Earthfile`:

```earthly
algo-extension-binary:
    # Extract the Ryugraph algo extension binary from the upstream
    # extension-repo image so Earthly can COPY it into the wrapper stage.
    # Earthly does not support COPY --from=<external-image>, so we wrap
    # the external image in a named target and SAVE ARTIFACT.
    FROM --platform=linux/amd64 ghcr.io/predictable-labs/extension-repo:latest
    SAVE ARTIFACT /usr/share/nginx/html/v25.9.0/linux_amd64/algo/libalgo.ryu_extension libalgo.ryu_extension

ryugraph-wrapper:
    FROM --platform=linux/amd64 python:3.12-slim
    # ... install ryugraph-wrapper and its deps ...

    # Bake algo extension binary into image (ADR-138).
    # Path uses 25.9.0 — that's Ryugraph's native library build version,
    # hardcoded in its extension loader. It is NOT the Python wheel version
    # (which resolves to 25.9.2 from PyPI). Mismatching the two causes
    # `LOAD algo` to silently fail at pod startup.
    RUN mkdir -p /root/.ryu/extension/25.9.0/linux_amd64/algo
    COPY +algo-extension-binary/libalgo.ryu_extension \
        /root/.ryu/extension/25.9.0/linux_amd64/algo/libalgo.ryu_extension
```

### Repo-split delivery: binary is pre-vendored in git, not pulled from ghcr.io at build time

The Earthly flow above works for **monorepo builds** (our CI and developer
laptops, which both have egress to `ghcr.io`). The **repo-split handoff** to
HSBC is different. HSBC's on-prem Airflow/Jenkins build hosts have no egress
to `ghcr.io` — the first revision of `tools/repo-split/build-repos.sh` tried
to `docker pull ghcr.io/predictable-labs/extension-repo:latest` at repo-split
time, which worked on our side (when *we* ran repo-split), but failed the
moment HSBC ran `make hsbc` / `make repo` themselves:

```
[INFO]   Fetching algo extension binary from ghcr.io/predictable-labs/extension-repo:latest (ADR-138)
Error response from daemon: Get https://ghcr.io/v2/: dial tcp: lookup ghcr.io on 169.254.169.254:53: no such host
[ERROR]   docker pull failed for ghcr.io/predictable-labs/extension-repo:latest
make: *** [Makefile:403: hsbc] Error 1
```

So the binary is now **committed to git** at
`tools/repo-split/vendor/libalgo.ryu_extension` (443 KB). At repo-split time
`fetch_algo_extension_binary()` in `tools/repo-split/build-repos.sh` simply
copies it into the per-repo `vendor/` directory — no `docker pull`, no
network call. The resulting handoff is fully self-contained; HSBC's Jenkins
only needs to `docker build`, which `COPY`s from `vendor/` via
`templates/Dockerfile.ryugraph-wrapper`.

`ghcr.io` access is now only required for **refreshing** the vendored binary
when Ryugraph bumps its native library version. That's done manually via
`tools/repo-split/refresh-algo-extension.sh` on a host with egress (i.e. us),
and the resulting binary is committed along with an updated
`tools/repo-split/vendor/README.md` (digest + hash + date) so the refresh is
reviewable in PRs. The monorepo Earthly flow (`+algo-extension-binary`) is
unaffected — it continues to pull from `ghcr.io` at build time, because that
runs on our infrastructure.

### The cache path uses the native library version `25.9.0`, NOT the Python wheel version

This is the most important thing to get right, and we did not get it right on the first
attempt. A pre-merge hive review caught it empirically.

**The trap:** the `ryugraph` Python wheel published on PyPI as of this writing is
`ryugraph 25.9.2`, so it is natural to assume that Ryugraph's extension cache lives under
`~/.ryu/extension/25.9.2/...`. It does not. The wheel version and the native library version
diverge: the C++ native library inside the wheel was built at version `25.9.0` and the
extension loader hardcodes that version string into its cache lookup path.

Evidence gathered during hive validation:

1. `pip install 'ryugraph>=25.9.2'` resolves to `ryugraph 25.9.2`.
   `python -c "import ryugraph; print(ryugraph.__version__)"` returns `25.9.2`.
2. The upstream `ghcr.io/predictable-labs/extension-repo:latest` image only publishes binaries
   under `/usr/share/nginx/html/v25.9.0/...`. There is no `v25.9.2/` directory.
3. Inspecting the Ryugraph shared library reveals the hardcoded path template
   `{}/.ryu/extension/{}/{}/` and a hardcoded URL segment
   `extension.ryugraph.io/v25.9.0/linux_amd64/algo/libalgo.ryu_extension` — proof that `25.9.0`
   is baked into the native binary itself, not read from `__version__`.
4. We ran this matrix inside a `python:3.12-slim --platform=linux/amd64` container with real
   `ryugraph==25.9.2` installed and the upstream binary extracted into the path under test:

   | Cache path | `LOAD algo` result |
   |---|---|
   | `/root/.ryu/extension/25.9.0/linux_amd64/algo/` | **success** |
   | `/root/.ryu/extension/25.9.2/linux_amd64/algo/` | fail — `Extension: algo is an official extension and has not been installed` |
   | `/root/.ryu/extension/v25.9.0/linux_amd64/algo/` | fail |
   | `/root/.ryu/extension/v25.9.2/linux_amd64/algo/` | fail |
   | `/root/.ryu/extension/25.9.0/algo/` (no arch) | fail |

The original plan was to capture `ryugraph.__version__` at build time via
`python -c "import ryugraph; print(ryugraph.__version__)"` and use it as the directory name,
under the assumption that the Python wheel version would match the cache-path version. That
assumption produced a cache at `.../25.9.2/...` which the runtime resolver silently ignores.
The wrapper would start cleanly (because the `LOAD algo` failure is caught and logged, not
raised), then every `/algo/pagerank` call would return the exact same
`function page_rank is not defined` error this ADR is meant to eliminate.

End-to-end validation in GKE London (UAT notebook `01_uat_validation` hitting a
freshly-spawned wrapper pod at image tag `hash-16c3e98295fe`) subsequently confirmed that the
hardcoded `25.9.0` path works and `CALL page_rank(...)` executes as expected. The wrapper pod's
events showed it pulled the new image, `LOAD algo` succeeded, and the UAT notebook completed
in ~43 seconds with zero algo-related failures.

**Rule to remember:** when Ryugraph bumps its upstream C++ native library version (not its
Python wheel version), the hardcoded `25.9.0` in the `Earthfile` bake path must be updated to
match. Verify the correct value by running
`strings /path/to/_ryugraph*.so | grep -A1 '\.ryu/extension'` inside the updated wheel, or by
checking which version directory the upstream extension-repo image actually publishes.

### Runtime: just `LOAD algo`

`packages/ryugraph-wrapper/src/wrapper/services/database.py` drops the
`INSTALL algo FROM '<url>'` step and the `RYUGRAPH_EXTENSION_SERVER_URL` env var lookup. The
only call left is:

```python
# packages/ryugraph-wrapper/src/wrapper/services/database.py - new flow
try:
    logger.info("Loading algo extension from local cache")
    self._connection.execute("LOAD algo")
    logger.info("Algo extension loaded successfully")
except Exception as e:
    logger.error(
        "Failed to load algo extension - native algorithms will not work",
        error=str(e),
        error_type=type(e).__name__,
    )
```

Because the binary is already at the cache path Ryugraph checks first, `LOAD algo` finds it
immediately, with no network call, no retry loop, and no dependency on another pod.

### httpfs dead code removed at the same time

The previous `_init_database()` also loaded the `httpfs` extension (for direct `gs://` reading
via S3-interoperability mode) and defined an unused `_load_data_direct_gcs()` method. The
httpfs production path was never actually used because GKE Workload Identity cannot supply the
S3-interop HMAC credentials that httpfs requires; the wrapper always falls back to downloading
files via the Python `google-cloud-storage` client and loading from local paths. The httpfs
`INSTALL`/`LOAD` block and the dead `_load_data_direct_gcs()` method are deleted in the same
commit set. See ADR-031 for the original dual-mode design and the reasoning for why the
emulator side of it still needs documenting.

### Helm and Terraform: delete the extension-server pod

The `extension-server` Helm `Deployment` and `Service` templates are removed from both the
`graph-olap` and `local-infra` charts. The wrapper `Deployment` no longer injects
`RYUGRAPH_EXTENSION_SERVER_URL` into wrapper pods. `extensionServer:` stanzas are removed from
all `values.yaml`/`values-*.yaml` files, from the control-plane ConfigMap template, from
`control_plane/config.py`, from `k8s_service.py`, from the `gcp-london-demo` Terraform
`main.tf`, from `tools/local-dev/k8s/e2e-stack.yaml`, from the repo-split config, and from the
`wait-for-ready.sh` / `deploy.sh` scripts. The HSBC-flat-YAML `control-plane-configmap.yaml` is
cleaned up as well (its previously-empty `GRAPH_OLAP_EXTENSION_SERVER_URL: ""` entry is
removed; control-plane `Settings` uses `extra="ignore"` so old configmaps with the stale key
still load cleanly on rollback).

---

## Consequences

### Positive

- **HSBC `/algo/*` endpoints just work.** No HSBC-side deployment changes, no extra pod, no
  configuration. The binary ships inside the image HSBC already runs.
- **No `extension-server` pod in any environment.** GKE London (`gcp-london-demo`), HSBC on-prem,
  local Orbstack, and E2E tests all lose the `extension-server` Deployment and its associated
  `Service`. One fewer Helm template, one fewer image to mirror, one fewer thing for HSBC
  operators to learn.
- **Faster wrapper startup.** The 1-6s INSTALL retry window is gone — wrapper init no longer
  waits on another pod's readiness.
- **Eliminates a class of races.** "Is `extension-server` ready yet?" was a real source of
  startup flakiness in GKE London. That race no longer exists, because there's nothing to race
  against.
- **Build-time visibility.** If the upstream extension-repo image is unavailable at build time,
  the wrapper image build fails immediately with a clear error, instead of producing an image
  that mysteriously fails at runtime in production.

### Negative

- **The cache path `25.9.0` is a hardcoded magic string.** It is the Ryugraph *native library*
  build version, not the Python wheel version, and the two can diverge. When Ryugraph bumps its
  native library version, both the `Earthfile` source path
  (`/usr/share/nginx/html/v{X}/...`) and the target path
  (`/root/.ryu/extension/{X}/linux_amd64/algo/...`) must be updated by hand. The rule for
  finding the correct value is documented above and in the Earthfile comment.
- **Build-time dependency on `ghcr.io/predictable-labs/extension-repo:latest` (monorepo only).**
  For monorepo Earthly builds the upstream image must be reachable at build time. The repo-split
  handoff no longer has this dependency — the binary is committed to git at
  `tools/repo-split/vendor/libalgo.ryu_extension` and refreshed manually via
  `tools/repo-split/refresh-algo-extension.sh`. HSBC Jenkins/Airflow need no `ghcr.io` egress.
- **Vendored binary (443 KB) in git.** The repo-split delivery path ships a pre-built AMD64 ELF
  binary in the monorepo. It must be refreshed manually when Ryugraph bumps its native library
  version; the refresh script prints digest + sha256 so `tools/repo-split/vendor/README.md` can
  be updated in the same commit for reviewability. Alternative (Git LFS) was considered but
  rejected as overkill for a 443 KB file refreshed rarely.
- **Still AMD64-only.** ADR-026's platform constraint still applies: the bundled binary is
  AMD64, so wrapper images must still be built `--platform=linux/amd64`. This ADR does not fix
  the upstream ARM64 packaging bug; it just removes the *runtime* extension-server dependency.

### Neutral

- **SDK endpoints unchanged.** `/algo/pagerank`, `/algo/wcc`, `/algo/louvain`, `/algo/kcore`,
  and `/algo/scc` continue to work exactly as before — same request bodies, same response
  shapes. The change is transparent to SDK callers.
- **`/networkx/*` remains available.** The in-process NetworkX algorithms are still there for
  workloads where users prefer NetworkX semantics, more parameters, or algorithms that the
  native extension does not implement.

---

## Alternatives Considered

### 1. Deploy `extension-server` in HSBC

**Rejected.** HSBC has explicitly declined to run an additional upstream image on their cluster
for this purpose, and we have no leverage to change that. Maintaining two code paths
("HSBC mode" without the pod and "everyone else" with the pod) is strictly worse than
collapsing both onto a single mode that doesn't need the pod at all.

### 2. Force clients to call `/networkx/pagerank` instead of `/algo/pagerank`

**Rejected.** NetworkX runs in-process in Python and is measurably slower than the native C++
algo extension on graphs of any meaningful size. It would also require rewriting notebooks,
SDK examples, and customer code that already targets `/algo/*`. We're keeping `/networkx/*`
available as an alternative for users who want it, but it is not a substitute for the native
endpoints.

### 3. Init container that fetches the binary once at pod startup

**Rejected.** This still introduces a second container (just short-lived instead of
long-running), still requires an extra Helm template, still requires the upstream image to be
reachable at runtime, and still has a startup-ordering relationship with the main wrapper
container. It has every downside of the current `extension-server` pod and no upside compared
to baking the binary into the image.

### 4. Resolve the cache directory dynamically from `ryugraph.__version__` at build time

**Tried and rejected.** This was the original plan. It produces a cache at
`/root/.ryu/extension/25.9.2/linux_amd64/algo/` because `pip install` currently resolves to
`ryugraph 25.9.2`. Ryugraph's runtime extension loader silently ignores this path and only
finds the binary at the hardcoded native-library-version path `.../25.9.0/...`. See the "cache
path uses the native library version" subsection above for the evidence matrix. The
dynamic-resolution approach feels more robust than a magic string, but it is quieter about
failure — `LOAD algo` fails silently in the wrapper startup try/except, the pod becomes
healthy, and the bug only surfaces when someone actually calls `/algo/pagerank`. Hardcoding
`25.9.0` is worse style but louder about going wrong: the `Earthfile` source path
`/usr/share/nginx/html/v25.9.0/linux_amd64/algo/libalgo.ryu_extension` will fail the image
build with a clear "file not found" error if the upstream image no longer publishes that
version.

---

## References

- [ADR-026: ARM64 Algo Extension Workaround (AMD64 Containers)](adr-026-arm64-algo-extension-workaround.md) — partially superseded by this ADR. The AMD64 platform constraint described in ADR-026 still applies; only the runtime `extension-server` dependency is removed.
- [ADR-031: Dual-Mode GCS Data Loading (Production vs Local)](--/system-design/adr-031-dual-mode-gcs-data-loading.md) — partially superseded by this ADR. The httpfs production loading path it decided on was never actually viable in GKE (Workload Identity cannot supply S3-interop HMAC credentials), and the related dead code is deleted in the same commit set as this ADR.
- [ADR-057: Cross-Platform Docker Builds for Cloud Deployment](adr-057-cross-platform-docker-builds-for-cloud-deployment.md) — documents the AMD64 build pipeline that this ADR continues to rely on.
- [ADR-076: Earthfile Build System Modernization](adr-076-earthfile-build-system-modernization.md) — defines the `+ryugraph-wrapper` target that is updated by this ADR. Also relevant for the `algo-extension-binary` target pattern used to lift files out of an external image.
- [Ryugraph Wrapper Services Design](--/--/--/component-designs/ryugraph-wrapper.services.design.md) — algo extension loading section, updated to reflect the new flow.
- `packages/ryugraph-wrapper/src/wrapper/services/database.py` — `_init_database()`, where the runtime `INSTALL` step and the httpfs block are removed.
- `Earthfile` — `algo-extension-binary` and `+ryugraph-wrapper` targets, where the binary is lifted out of the upstream image and baked into the wrapper image.
- [ARM64 Workaround Documentation](--/--/--/platform/extensions/arm64-workaround-mdx) — historical context for the platform constraint, with an admonition pointing back to this ADR.
