# Public OSF Fetch Target

This directory is a local fetch target for the authors' public OSF release.

The repository does not re-host the OSF files directly. To download the small public bundle used by the historical rerun, run:

```bash
python3 scripts/fetch_public_osf_release.py
```

That command downloads the exact public files this repo expects into `osf/`.
