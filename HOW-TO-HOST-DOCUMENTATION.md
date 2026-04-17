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

### Step 1: Get the Zip File

`documentation-site.zip` (10 MB) — shared separately.

### Step 2: Copy to Your Server

```bash
scp documentation-site.zip user@your-server:/tmp/
```

### Step 3: Log into the Server

```bash
ssh user@your-server
```

### Step 4: Extract the Zip

```bash
cd /tmp
unzip documentation-site.zip
```

### Step 5: Verify the Extraction

```bash
ls /tmp/dist/
```

**What you should see:**

```
404.html  _astro  api  architecture  component-designs  decision-records  developer-guide  diagrams  governance  hsbc-deployment  index.html  ...
```

**You must see `index.html` in the list.** If you don't see it, the extraction failed — try `unzip` again or check the zip file.

### Step 6: Serve the Site

You only need ONE of the following. Pick whichever is installed on the server.

**Python (most Linux servers have this):**

```bash
cd /tmp/dist
python3 -m http.server 3000
```

**nginx (if already installed):**

```bash
sudo cp -r /tmp/dist/* /usr/share/nginx/html/
sudo systemctl restart nginx
```

### Step 7: Verify the Site is Running

**If using Python:**

Open a new terminal (keep the Python server running in the first one) and run:

```bash
curl http://localhost:3000/
```

**If using nginx:**

```bash
curl http://localhost/
```

**What you should see:** HTML content starting with `<!DOCTYPE html>` and containing "Graph OLAP Platform".

**If you see this HTML:** the site is working.

**If you see "connection refused":**

- Python: make sure the `python3 -m http.server 3000` command is still running in the other terminal
- nginx: run `sudo systemctl status nginx` to check if nginx is running

### Step 8: Open in Your Browser

- If using Python: `http://<server-ip>:3000`
- If using nginx: `http://<server-ip>`

You should see the Graph OLAP Platform documentation site with a dark-themed sidebar on the left and content on the right.

**To stop the Python server:** press `Ctrl+C` in the terminal where it is running.
