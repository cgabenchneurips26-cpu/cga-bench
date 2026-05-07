# CGA-Bench Release Runbook

End-to-end checklist for publishing the dataset (HuggingFace) and the
anonymized code copy (anon4openreview / Zenodo / anon GitHub) so the
NeurIPS 2026 D&B submission satisfies:

- Dataset hosted on a preferred ML host (Dataverse / Kaggle / HF / OpenML)
- Code accessible without personal request (anonymized)
- Croissant metadata file (Core + RAI fields) downloadable from the
  hosted dataset, with valid `url` / `contentUrl` fields
- Both data and code reachable by reviewers/ACs/SACs at submission time

The three release scripts that automate this live under
`scripts/release/`:

| Script | Purpose |
|---|---|
| `upload_dataset_hf.py` | HuggingFace dataset upload |
| `package_anon.sh`      | Tarball + SHA-256 + manifest for anon code host |
| `update_croissant_urls.py` | Patch live URLs into croissant.json after upload |

---

## Step 0 — Prerequisites

1. Python 3.10+ environment with the project's deps installed.
2. `pip install -U huggingface_hub mlcroissant` (release-only deps).
3. **Anonymous HuggingFace account** (do not use your real account):
   - Create at <https://huggingface.co/join> with a throwaway alias.
   - Generate a write token at <https://huggingface.co/settings/tokens>.
   - Export it: `export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx`
4. Decide an anonymous code host:
   - **anon4openreview.com** (NeurIPS recommended) — simple ZIP upload.
   - **Zenodo** anonymous deposit — gives a DOI.
   - **GitHub** anonymous account — force-push without history.

---

## Step 1 — Verify the local submission tree is clean

```bash
cd cga_bench/   # or cga_bench_submission/

# Verifier (11 critical files + 25 graphs + 19 imports):
python scripts/submission/prepare_submission.py \
    --source . --dest . --verify-only

# Croissant validates locally:
python -c "
import mlcroissant
ds = mlcroissant.Dataset(jsonld='croissant.json')
print(f'OK {ds.metadata.name} v{ds.metadata.version} n_dist={len(ds.metadata.distribution)}')
"
```

Both must pass before continuing.

---

## Step 2 — Upload dataset to HuggingFace

```bash
HF_TOKEN=hf_xxxxxxxx python3 scripts/release/upload_dataset_hf.py \
    --repo-id <anon-user>/cga-bench \
    --source . \
    --commit-message "Initial CGA-Bench v7.3 upload"
```

The script applies a strict `IGNORE_PATTERNS` (paper, secrets, anon copy,
caches, intermediate runs) so the HF mirror only carries reviewer-relevant
content. After completion you should see:

> View: <https://huggingface.co/datasets/anon-user/cga-bench>

Visit the page once and confirm:

- README.md renders.
- DATASHEET.md is browsable.
- `evidence_pack/`, `data/`, `cpg_model/graphs/`, `configs/scenarios/`
  trees are present.
- `croissant.json` is downloadable.

---

## Step 3 — Patch croissant.json with live URLs

```bash
python3 scripts/release/update_croissant_urls.py \
    --croissant croissant.json \
    --hf-repo <anon-user>/cga-bench
```

This rewrites `url` to `https://huggingface.co/datasets/<anon-user>/cga-bench`
and updates each `distribution[].contentUrl` whose host still matches a
placeholder (`anonymous/cga-bench`, `anonymous`, etc.) to point at
`https://huggingface.co/datasets/<anon-user>/cga-bench/resolve/main/<path>`.

After patching, the script re-validates with `mlcroissant`. **Re-upload
the patched croissant.json to HF** so the live copy carries the same URLs
as the local copy:

```bash
python3 scripts/release/upload_dataset_hf.py \
    --repo-id <anon-user>/cga-bench --source . \
    --commit-message "Patch croissant.json url + contentUrls"
```

Final check — the NeurIPS-recommended online validator:

> <https://croissant.mlcommons.org/validator>

paste the public URL of `croissant.json` from the HF dataset (raw view).
It should report Core + RAI conformance.

---

## Step 4 — Package the anonymized code copy

```bash
# Re-run the anonymizer (only if anonymous_repo/ is stale):
python3 scripts/prepare_anonymous_repo.py

# Build the upload bundle:
bash scripts/release/package_anon.sh \
    --source ../anonymous_repo \
    --tag v7.3
```

Outputs in `release/`:

- `cga_bench_anon_v7.3.tar.gz`
- `cga_bench_anon_v7.3.tar.gz.sha256`
- `cga_bench_anon_v7.3.MANIFEST.txt`

---

## Step 5 — Upload the anonymized code

Pick **one** host and follow its flow:

### 5a. anon4openreview (NeurIPS preferred)

1. Visit <https://anonymous.4open.science/>.
2. Click "Upload your code" → upload `cga_bench_anon_v7.3.tar.gz`.
3. Note the assigned read-only URL, e.g.
   `https://anonymous.4open.science/r/cga-bench-XXXX/`.

### 5b. Zenodo anonymous deposit

1. <https://zenodo.org/uploads/new> with the anonymous alias.
2. Set "Restricted" → "Anonymous Review Access".
3. Upload the tarball, note the DOI / share link.

### 5c. Anonymous GitHub mirror

1. Create empty repo `<anon-user>/cga-bench` (no README, no init).
2. From the anonymized tree:

   ```bash
   cd anonymous_repo
   git init -b main
   git add -A
   git commit -m "Initial CGA-Bench v7.3 anonymous release"
   git remote add origin https://github.com/<anon-user>/cga-bench.git
   git push -f origin main
   ```

   `git init` + single force-push avoids leaking the dev history.

---

## Step 6 — Update the OpenReview submission

In the OpenReview submission form, attach **both**:

- **Croissant metadata file** — the patched `croissant.json` from Step 3.
- **Code link** — the anon4openreview / Zenodo / anon GitHub URL from Step 5.
- **Dataset link** — the HuggingFace dataset URL from Step 2.

Some venues also expect the supplementary ZIP — use
`cga_bench_anon_v7.3.tar.gz` from Step 4.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `huggingface_hub.utils.HfHubHTTPError: 401` | `HF_TOKEN` invalid or missing write scope. Regenerate at HF settings. |
| Upload hangs at one large file | HF re-uses LFS for binaries; first push of a 100 MB+ file can stall on slow links. Re-run; the SDK resumes. |
| `mlcroissant` validation error after URL patch | Re-run `update_croissant_urls.py` — the patch may not have been called with `--hf-repo` and `contentUrl` field still references a placeholder. |
| anon4openreview rejects the ZIP | Repackage as `.zip` (not `.tar.gz`) — some flows accept only zip. `cd release && unzip cga_bench_anon_v7.3.tar.gz && zip -r cga_bench_anon_v7.3.zip cga_bench/` |
| Reviewer reports broken `contentUrl` | The HF tree path differs from the local path (e.g., a renamed folder). Edit `croissant.json` distribution[].contentUrl manually and re-upload. |

---

## Post-submission maintenance

- Camera-ready: replace the anonymous identifiers (HF account, code URL,
  citation) with the real ones in `croissant.json` and re-upload.
- Future versions: bump `version` in `croissant.json`, repeat Steps 2-3.
- Backup: keep a tagged release of the **non-anonymized** repo locally
  (the dev `cga_bench/`) — that is the source of truth for any reproduction
  questions during review.
