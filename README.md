# DrainTool Mobile

This repo now includes a cloud-ready Flask web app version of the original DrainTool desktop project.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python web_app.py
```

Then open `http://localhost:8000`.

## Cloud deploy

Render is the easiest option for this project because it supports a persistent disk for drain data and uploaded photos.

### Render

This repo now includes [render.yaml](C:/Users/hazao/Downloads/DrainTool/render.yaml), which sets up:

- a Python web service
- `gunicorn` startup
- a persistent disk mounted at `/var/data`
- `DRAINTOOL_DATA_DIR=/var/data` so drain edits and uploaded photos survive restarts

Steps:

1. Push this folder to GitHub.
2. In Render, create a new Blueprint and point it at the repo.
3. Render will read `render.yaml` and provision the app plus persistent disk.
4. Open the deployed URL in Safari or any browser.

### Manual deploy on Render or Railway

Use:

- Install command: `pip install -r requirements.txt`
- Start command: `gunicorn -b 0.0.0.0:$PORT web_app:app`

Recommended environment variables:

- `DRAINTOOL_DATA_DIR`
  Set this to your mounted persistent storage path.
- `FLASK_SECRET_KEY`
  Set a private random value.

### Railway

Railway is a strong free-tier option for this app because it can attach a small persistent volume.

Steps:

1. Push this repo to GitHub.
2. In Railway, create a new project from the GitHub repo.
3. Add a volume in the Railway project.
4. Railway exposes the mount path as `RAILWAY_VOLUME_MOUNT_PATH`.
5. DrainTool will automatically use that mounted path for live data unless you override `DRAINTOOL_DATA_DIR`.

Recommended Railway variables:

- `FLASK_SECRET_KEY`
  Set a private random value.
- `PORT`
  Railway usually provides this automatically.

You can keep editing the app locally after deployment and redeploy updated versions whenever you want. Deployment does not stop this workspace from being the source of truth.

## iPhone use

After deployment, open the site in Safari and use `Share -> Add to Home Screen` to launch it like a standalone app.

## What is included

- Mobile-first planner page
- Session recommendations
- Compact route builder
- Drain detail pages
- Metadata editing for visited/favorite/notes
- Custom drain creation
- Persistent uploaded-photo storage when deployed with a mounted data disk
- Manual `Sync Map` support for pulling a shared Google Earth / Drive KML or KMZ into the live drain list

## Persistent storage behavior

- Locally, the app still uses this folder by default.
- In the cloud, set `DRAINTOOL_DATA_DIR` to a persistent mounted directory.
- On first boot, the app copies the bundled `drain_data.json` into that data directory if no live data file exists yet.
- Uploaded drain photos are stored in `<data dir>/uploads`.

## Still worth knowing

- Existing old photo references that point to absolute paths on your PC are still local-machine references. Those will not work from the cloud unless the actual images are copied into the mounted data folder or uploaded through the web UI.
- Large music files are still served from the app bundle right now, which is fine for initial deployment but could be moved to object storage later if you want a cleaner production setup.
- The `Sync Map` button expects the shared Google Drive / Google Earth file to be publicly downloadable as KML or KMZ.
