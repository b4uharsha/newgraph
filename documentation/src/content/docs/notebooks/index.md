---
title: "Notebooks"
description: "Jupyter notebooks rendered as static pages — tutorials, SDK reference, end-to-end tests, and UAT."
---

This section collects the platform's Jupyter notebooks, converted to static pages at build time.
The notebooks remain the source of truth; this rendering is generated from the `.ipynb` files on every build.

- **Tutorial** — hands-on walkthroughs for analysts (`docs/notebooks/tutorials/`)
- **Reference** — API reference notebooks per SDK resource (`docs/notebooks/reference/`)
- **E2E** — end-to-end platform test notebooks (`tests/e2e/notebooks/platform-tests/`)
- **UAT** — user acceptance test notebooks (`docs/notebooks/uat/`)

To run any of these notebooks interactively, open them in JupyterHub with a configured `GraphOLAPClient`.
