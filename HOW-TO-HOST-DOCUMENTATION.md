# How to Host the Documentation Site

The documentation site was migrated from MkDocs (Python) to **Astro/Starlight** (Node.js). There are two ways to host it. Pick whichever is easier for your team.

---

## Option 1: Build the Docker Image via Jenkins (CI/CD)

This is the same approach used for all other services (control-plane, export-worker, etc.).

### Step 1: Get Node.js 22 on the Jenkins Build Agent

You need Node.js 22 on the build agent. Pick one of these ways to get it:

**Way A — NodeJS Jenkins Plugin:**

- Go to Jenkins → Manage Jenkins → Tools → NodeJS installations → Add NodeJS 22
- In your pipeline, wrap the build step with `nodejs('NodeJS-22') { ... }`

**Way B — Ask the CICD Central Team:**

- Request them to add Node.js 22 LTS to your build agent
- It has been the LTS version since October 2024

**Way C — Install manually on the build agent:**

Ubuntu / Debian:

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash -
sudo apt-get install -y nodejs
```

RHEL / CentOS:

```bash
curl -fsSL https://rpm.nodesource.com/setup_22.x | sudo bash -
sudo yum install -y nodejs
```

Using nvm (any Linux):

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
nvm install 22
nvm use 22
```

### Step 2: Verify Node.js Installation

Run these commands on the Jenkins build agent:

```bash
node -v
npm -v
```

**What you should see:**

```
$ node -v
v22.x.x       <-- must be v22 or higher. If it shows v10, v14, v16, v18, or v20, it is too old.

$ npm -v
9.x.x         <-- must be 9 or higher. npm ships with Node, so if Node is correct, npm will be too.
```

**If `node -v` shows the wrong version or "command not found":**

- Node.js is not installed or not on the PATH
- Go back to Step 1 and try a different way
- If using nvm, make sure you ran `nvm use 22`

**If `node -v` shows v22 or higher:** you are ready. Move to Step 3.

### Step 3: Build the Docker Image

```bash
cd documentation
docker build -t documentation:latest .
```

**What you should see at the end:**

```
Successfully built <image-id>
Successfully tagged documentation:latest
```

**If the build fails:**

- Check the error message. Common issues:
  - `npm ci` fails → npm registry not reachable (ask CICD team about Nexus npm mirror)
  - `COPY build/hsbc_root.cer` fails → the `build/` directory is missing HSBC certificates
  - `apt-get install` fails → APT mirror not reachable from inside the container

### Step 4: Verify the Docker Image Works

Run the image locally on the build agent to check it works before pushing:

```bash
docker run -d --name docs-test -p 3000:3000 documentation:latest
```

Then check it:

```bash
curl http://localhost:3000/
```

**What you should see:** HTML content starting with `<!DOCTYPE html>` and containing "Graph OLAP Platform".

**If you see HTML:** the image is working. Stop the test container and move to Step 5:

```bash
docker stop docs-test
docker rm docs-test
```

**If `curl` returns "connection refused" or empty:** the container failed to start. Check logs:

```bash
docker logs docs-test
```

### Step 5: Push the Image to Your Registry

```bash
docker tag documentation:latest gcr.io/<your-project>/documentation:<version>
docker push gcr.io/<your-project>/documentation:<version>
```

**What you should see:** upload progress bars, then `latest: digest: sha256:...`

### Step 6: Update the Deployment

Open `cd/resources/documentation-deployment.yaml` and update the image tag on line 42:

```yaml
image: gcr.io/<your-project>/documentation:<version>
```

### Step 7: Apply the Deployment

```bash
kubectl apply -f cd/resources/documentation-deployment.yaml
```

### Step 8: Verify the Deployment

```bash
kubectl get pods -n graph-olap-platform | grep documentation
```

**What you should see:**

```
graph-olap-documentation-xxxxx   1/1   Running   0   <age>
```

- `1/1` means the container is running and healthy
- `Running` means it started successfully

**If you see `0/1` or `CrashLoopBackOff`:** the container is failing. Check logs:

```bash
kubectl logs -n graph-olap-platform -l app=documentation
```

**Final check — open in your browser:**

```
http://<your-cluster-documentation-url>
```

You should see the Graph OLAP Platform documentation site with a dark-themed sidebar on the left and content on the right.

---

## Option 2: Pre-Built Static Site (No Build Needed)

The documentation site is already built. No Node.js, no npm, no Docker, no internet required. Just extract and serve.

### What is in the zip?

`documentation-site.zip` (10 MB) contains a folder called `dist/` with 193 pre-built HTML pages, CSS, JavaScript, images, and diagrams. This is the complete documentation site, ready to serve.

### Step 1: Download the Zip File

Download `documentation-site.zip` from the link shared separately.

Save it somewhere you can find it. For example, your Downloads folder or Desktop.

### Step 2: Extract the Zip on Your Local Machine

**Linux / macOS:**

```bash
cd ~/Downloads
unzip documentation-site.zip
```

**Windows:**

Right-click `documentation-site.zip` → Extract All → Choose a folder → Click Extract.

This creates a folder called `dist/`.

### Step 3: Verify the Extraction

**Linux / macOS:**

```bash
ls dist/
```

**Windows:**

Open the `dist` folder in File Explorer.

**What you should see inside `dist/`:**

```
404.html
_astro/
api/
architecture/
component-designs/
decision-records/
developer-guide/
diagrams/
governance/
hsbc-deployment/
index.html
notebooks/
operations/
sdk-manual/
security/
standards/
```

**You must see `index.html` in the list.** If you don't see it, the extraction failed — try again or check the zip file.

### Step 4: Copy to your server (if hosting on a remote server)

If you want to host on a remote server, copy the `dist/` folder to it:

```bash
scp -r dist/ user@your-server:/tmp/dist/
```

If you want to host it on the same machine you extracted on, skip this step — just use the `dist/` folder where it is.

If you want to host on GCS, skip this step — go straight to Way C below.

### Step 6: Serve the Site

You only need ONE of the following. Pick whichever is available to your team.

---

**Way A — Python (most Linux servers have this):**

Go to the `dist/` folder (wherever you extracted or copied it) and start the server:

```bash
cd /path/to/dist
python3 -m http.server 3000
```

For example, if you extracted on the server at `/tmp`:

```bash
cd /tmp/dist
python3 -m http.server 3000
```

**Verify:**

Open a new terminal (keep the Python server running in the first one) and run:

```bash
curl http://localhost:3000/
```

**What you should see:** HTML content starting with `<!DOCTYPE html>` and containing "Graph OLAP Platform".

**If you see "connection refused":** make sure the `python3 -m http.server 3000` command is still running in the other terminal.

**Open in your browser:** `http://<server-ip>:3000`

**To stop the server:** press `Ctrl+C` in the terminal where it is running.

---

**Way B — nginx (if already installed):**

Copy the contents of the `dist/` folder to nginx's default web root:

```bash
sudo cp -r /path/to/dist/* /usr/share/nginx/html/
sudo systemctl restart nginx
```

For example, if you extracted on the server at `/tmp`:

```bash
sudo cp -r /tmp/dist/* /usr/share/nginx/html/
sudo systemctl restart nginx
```

**Verify:**

```bash
curl http://localhost/
```

**What you should see:** HTML content starting with `<!DOCTYPE html>` and containing "Graph OLAP Platform".

**If you see "connection refused":** run `sudo systemctl status nginx` to check if nginx is running.

**Open in your browser:** `http://<server-ip>`

---

**Way C — Google Cloud Storage (GCS bucket):**

This hosts the site as a static website on GCS. No server needed — GCS serves the files directly.

**Step C.1: Create a GCS bucket (skip if you already have one):**

```bash
gsutil mb -p <your-gcp-project> -l <your-region> gs://<your-bucket-name>
```

Example:

```bash
gsutil mb -p hsbc-12636856-udlhk-dev -l europe-west2 gs://graph-olap-docs
```

**Step C.2: Upload the `dist/` folder contents to the bucket:**

Go to the folder where you extracted the zip (e.g. `~/Downloads` or `/tmp`):

```bash
cd ~/Downloads
gsutil -m cp -r dist/* gs://<your-bucket-name>/
```

Example:

```bash
cd ~/Downloads
gsutil -m cp -r dist/* gs://graph-olap-docs/
```

This uploads all 193 pages, CSS, JavaScript, images, and diagrams to the bucket.

**What you should see:** lines showing each file being uploaded, ending with `Operation completed`.

**Step C.3: Configure the bucket for static website hosting:**

```bash
gsutil web set -m index.html -e 404.html gs://<your-bucket-name>
```

**Step C.4: Make the bucket publicly readable (or use IAM for internal access):**

For internal access only (recommended):

```bash
gsutil iam ch allUsers:objectViewer gs://<your-bucket-name>
```

Or if your org uses IAM groups, replace `allUsers` with your group:

```bash
gsutil iam ch group:<your-team>@hsbc.com:objectViewer gs://<your-bucket-name>
```

**Step C.5: Get the website URL:**

```bash
echo "http://storage.googleapis.com/<your-bucket-name>/index.html"
```

Or if you have a load balancer in front of the bucket:

```bash
echo "https://<your-domain>"
```

**Verify:**

Open the URL in your browser. You should see the Graph OLAP Platform documentation site with a dark-themed sidebar on the left and content on the right.

**If you see "Access Denied":** the IAM permissions from Step C.4 are not applied. Run the `gsutil iam ch` command again and wait 1-2 minutes for it to take effect.

**If you see a blank page or XML error:** the `gsutil web set` command from Step C.3 was not run. Run it and try again.

**To update the site later:** just upload the new files again:

```bash
gsutil -m cp -r dist/* gs://<your-bucket-name>/
```

---

### Step 7: Final Check

Whichever way you chose (Python, nginx, or GCS), open the URL in your browser. You should see the Graph OLAP Platform documentation site with a dark-themed sidebar on the left and content on the right.
