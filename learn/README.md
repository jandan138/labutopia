# LabUtopia Learn Guide

This folder contains a static interactive tutorial for understanding the LabUtopia repository.

Open it with a local HTTP server from the repository root, not from `learn/`.
The page references project images in `images/`, so the repository root should be
the server root:

```bash
cd /cpfs/shared/simulation/zhuzihou/dev/LabUtopia
python3 -m http.server 8099
```

Then visit:

```text
http://127.0.0.1:8099/learn/index.html
```

The page is intentionally self-contained: no build step, no npm install, and no external JavaScript runtime.
