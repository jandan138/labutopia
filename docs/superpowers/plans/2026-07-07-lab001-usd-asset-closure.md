# Lab001 USD Asset Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a portable directory package for `assets/chemistry_lab/lab_001/lab_001.usd` and verify whether it can open without depending on the original source directory.

**Architecture:** Use the bundled USD/Isaac `pxr.UsdUtils.LocalizeAsset` API as the first-pass collect/pack mechanism. Verify the resulting package from an independent clean copy, then only perform targeted remediation for unresolved Isaac cabinet payloads and MDL modules if the first-pass package still has missing dependencies.

**Tech Stack:** Python 3.10, `pxr.Usd`, `pxr.Sdf`, `pxr.UsdUtils`, Isaac Sim bundled USD libraries, shell verification commands.

---

### Task 1: Baseline Dependency Inventory

**Files:**
- Read: `assets/chemistry_lab/lab_001/lab_001.usd`
- Create: `outputs/usd_asset_packages/lab_001_baseline_20260707.txt`

- [ ] **Step 1: Create output report directory**

Run:
```bash
mkdir -p outputs/usd_asset_packages
```

Expected: command exits `0`.

- [ ] **Step 2: Record baseline dependency closure**

Run:
```bash
python - <<'PY' > outputs/usd_asset_packages/lab_001_baseline_20260707.txt
from pathlib import Path
from pxr import Usd, UsdUtils

src = Path("assets/chemistry_lab/lab_001/lab_001.usd").resolve()
stage = Usd.Stage.Open(str(src), load=Usd.Stage.LoadNone)
print(f"source={src}")
print(f"stage_open={bool(stage)}")
if stage:
    print(f"default_prim={stage.GetDefaultPrim().GetPath() if stage.GetDefaultPrim() else None}")
    print(f"root_sublayers={list(stage.GetRootLayer().subLayerPaths)}")
    mesh_count = sum(1 for prim in stage.TraverseAll() if prim.GetTypeName() == "Mesh")
    print(f"mesh_count={mesh_count}")

layers, assets, unresolved = UsdUtils.ComputeAllDependencies(str(src))
print(f"dependency_layers={len(layers)}")
print(f"dependency_assets={len(assets)}")
print(f"unresolved={len(unresolved)}")
print("assets:")
for item in sorted(str(asset) for asset in assets):
    print(f"  {item}")
print("unresolved_assets:")
for item in sorted(str(asset) for asset in unresolved):
    print(f"  {item}")
PY
```

Expected: report is written and lists the first-pass dependency state.

### Task 2: First-Pass USD LocalizeAsset Package

**Files:**
- Read: `assets/chemistry_lab/lab_001/lab_001.usd`
- Create: `outputs/usd_asset_packages/lab_001_localized_20260707/lab_001.usd`
- Create: `outputs/usd_asset_packages/lab_001_localized_20260707/_reports/localize_asset.log`

- [ ] **Step 1: Recreate package directory without touching the source asset**

Run:
```bash
rm -rf outputs/usd_asset_packages/lab_001_localized_20260707
mkdir -p outputs/usd_asset_packages/lab_001_localized_20260707
```

Expected: package directory exists and source directory remains unchanged.

- [ ] **Step 2: Run USD LocalizeAsset**

Run:
```bash
python - <<'PY' 2>&1 | tee outputs/usd_asset_packages/lab_001_localized_20260707/_reports.localize_asset.log
from pathlib import Path
from pxr import Sdf, UsdUtils

src = Path("assets/chemistry_lab/lab_001/lab_001.usd").resolve()
dst = Path("outputs/usd_asset_packages/lab_001_localized_20260707").resolve()
ok = UsdUtils.LocalizeAsset(Sdf.AssetPath(str(src)), str(dst), False)
print(f"localize_asset_return={ok}")
print(f"package_dir={dst}")
print(f"root_exists={(dst / 'lab_001.usd').exists()}")
PY
```

Expected: `root_exists=True`. Warnings are acceptable at this step if they correspond to unresolved remote or MDL assets that will be evaluated in Task 3.

- [ ] **Step 3: Move the localize log into `_reports` if the command wrote it before the directory existed**

Run:
```bash
mkdir -p outputs/usd_asset_packages/lab_001_localized_20260707/_reports
test ! -f outputs/usd_asset_packages/lab_001_localized_20260707/_reports.localize_asset.log || mv outputs/usd_asset_packages/lab_001_localized_20260707/_reports.localize_asset.log outputs/usd_asset_packages/lab_001_localized_20260707/_reports/localize_asset.log
```

Expected: `_reports/localize_asset.log` exists if the localize command produced output through `tee`.

### Task 3: Clean-Copy Verification

**Files:**
- Read: `outputs/usd_asset_packages/lab_001_localized_20260707/lab_001.usd`
- Create: `/tmp/lab001_clean_verify_20260707`
- Create: `outputs/usd_asset_packages/lab_001_localized_20260707/_reports/clean_verify.txt`

- [ ] **Step 1: Copy the package to an unrelated clean path**

Run:
```bash
rm -rf /tmp/lab001_clean_verify_20260707
mkdir -p /tmp/lab001_clean_verify_20260707
cp -a outputs/usd_asset_packages/lab_001_localized_20260707/. /tmp/lab001_clean_verify_20260707/
```

Expected: clean copy exists outside the original asset tree.

- [ ] **Step 2: Verify stage open, dependency closure, and path containment from the clean copy**

Run:
```bash
python - <<'PY' > outputs/usd_asset_packages/lab_001_localized_20260707/_reports/clean_verify.txt
from pathlib import Path
from pxr import Usd, UsdUtils

pkg = Path("/tmp/lab001_clean_verify_20260707").resolve()
root = pkg / "lab_001.usd"
original = Path("assets/chemistry_lab/lab_001").resolve()
stage = Usd.Stage.Open(str(root), load=Usd.Stage.LoadNone)
print(f"clean_root={root}")
print(f"stage_open_load_none={bool(stage)}")
if stage:
    print(f"default_prim={stage.GetDefaultPrim().GetPath() if stage.GetDefaultPrim() else None}")

layers, assets, unresolved = UsdUtils.ComputeAllDependencies(str(root))
print(f"dependency_layers={len(layers)}")
print(f"dependency_assets={len(assets)}")
print(f"unresolved={len(unresolved)}")

def is_inside(path, parent):
    try:
        Path(path).resolve().relative_to(parent)
        return True
    except Exception:
        return False

outside_layers = []
for layer in layers:
    path = getattr(layer, "realPath", "") or getattr(layer, "identifier", "")
    if path and Path(path).is_absolute() and not is_inside(path, pkg):
        outside_layers.append(path)

outside_assets = []
for asset in assets:
    s = str(asset)
    if s and Path(s).is_absolute() and not is_inside(s, pkg):
        outside_assets.append(s)

print("outside_layers:")
for item in sorted(outside_layers):
    print(f"  {item}")
print("outside_assets:")
for item in sorted(outside_assets):
    print(f"  {item}")
print("unresolved_assets:")
for item in sorted(str(asset) for asset in unresolved):
    print(f"  {item}")
print(f"references_original_source={any(str(original) in item for item in outside_layers + outside_assets)}")
PY
```

Expected: `stage_open_load_none=True`; `references_original_source=False`; any remaining unresolved assets are explicitly listed.

### Task 4: Targeted Remediation Decision

**Files:**
- Read: `outputs/usd_asset_packages/lab_001_localized_20260707/_reports/clean_verify.txt`
- Create: `outputs/usd_asset_packages/lab_001_localized_20260707/_reports/remediation_decision.txt`

- [ ] **Step 1: Classify unresolved dependency names**

Run:
```bash
python - <<'PY' > outputs/usd_asset_packages/lab_001_localized_20260707/_reports/remediation_decision.txt
from pathlib import Path

report = Path("outputs/usd_asset_packages/lab_001_localized_20260707/_reports/clean_verify.txt")
text = report.read_text()
unresolved = []
capture = False
for line in text.splitlines():
    if line == "unresolved_assets:":
        capture = True
        continue
    if capture and line.startswith("  "):
        unresolved.append(line.strip())
    elif capture:
        break

cabinet = [x for x in unresolved if "Sektion_Cabinet" in x or "sektion_cabinet" in x]
mdl = [x for x in unresolved if x.endswith(".mdl") or ".mdl" in x]
other = [x for x in unresolved if x not in cabinet and x not in mdl]

print(f"unresolved_count={len(unresolved)}")
print(f"cabinet_count={len(cabinet)}")
for x in cabinet:
    print(f"cabinet {x}")
print(f"mdl_count={len(mdl)}")
for x in mdl:
    print(f"mdl {x}")
print(f"other_count={len(other)}")
for x in other:
    print(f"other {x}")
print(f"needs_targeted_remediation={bool(cabinet or mdl)}")
PY
```

Expected: decision report states whether cabinet or MDL remediation is needed.

- [ ] **Step 2: Stop before convertasset if unresolved assets are only built-in MDL modules**

Run:
```bash
sed -n '1,120p' outputs/usd_asset_packages/lab_001_localized_20260707/_reports/remediation_decision.txt
```

Expected: If `cabinet_count=0` and unresolved MDLs are only `OmniPBR.mdl`, `OmniGlass.mdl`, `OmniSurfacePresets.mdl`, or `gltf/pbr.mdl`, keep the package and document the Isaac Sim runtime requirement rather than introducing convertasset.

- [ ] **Step 3: Use targeted script remediation only if cabinet or remote MDL assets remain unresolved**

Run only when `needs_targeted_remediation=True`:
```bash
python - <<'PY'
print("Targeted remediation is required. Implement one focused script that downloads or copies the specific missing assets, rewrites only their asset paths in the localized root layer, and then reruns Task 3.")
PY
```

Expected: no broad asset conversion is performed before the unresolved asset list proves it is necessary.

### Task 5: Final Verification Summary

**Files:**
- Read: `outputs/usd_asset_packages/lab_001_localized_20260707/_reports/*.txt`
- Create: `outputs/usd_asset_packages/lab_001_localized_20260707/README_LAB001_PACKAGE.md`

- [ ] **Step 1: Write a concise package README from the verified reports**

Run:
```bash
python - <<'PY'
from pathlib import Path

pkg = Path("outputs/usd_asset_packages/lab_001_localized_20260707")
clean = (pkg / "_reports" / "clean_verify.txt").read_text()
decision = (pkg / "_reports" / "remediation_decision.txt").read_text()
readme = pkg / "README_LAB001_PACKAGE.md"
readme.write_text(
    "# Lab 001 USD Package\n\n"
    "Root file: `lab_001.usd`\n\n"
    "This package was produced with `pxr.UsdUtils.LocalizeAsset` from "
    "`assets/chemistry_lab/lab_001/lab_001.usd` and verified from `/tmp/lab001_clean_verify_20260707`.\n\n"
    "## Clean Verification\n\n"
    "```text\n" + clean.strip() + "\n```\n\n"
    "## Remediation Decision\n\n"
    "```text\n" + decision.strip() + "\n```\n",
    encoding="utf-8",
)
print(readme)
PY
```

Expected: README exists and cites the clean verification result.

- [ ] **Step 2: Report git-visible changes**

Run:
```bash
git status --short
```

Expected: source asset remains unmodified; package contents under `outputs/` are ignored by git; the only tracked-path addition is this plan file unless follow-up documentation is added intentionally.
