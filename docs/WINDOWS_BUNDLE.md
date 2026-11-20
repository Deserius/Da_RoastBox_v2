# Prepared Windows download: contents and verification

**Entry point: `thelaunch.bat`.** Extract the complete ZIP before launching.
See [local instructions](LOCAL_INSTALL.md) for setup, browser/audio controls and
preservation safeguards. This changes the downloadable launcher, not the running
workspace app/database or the pending cloud/new-project scope.

## Prepared, not an empty installer template

The release tree was assembled in an isolated build cache using:

- Official PSF **Python 3.13.16 Windows x64 NuGet** files. The archive's SHA512 was
  checked against official NuGet response metadata. Core binaries include embedded
  PSF signing certificates; actual Windows trust validation is performed by the BAT/
  PowerShell path on the recipient's PC, not certified by this Linux build.
- **50 locked Windows-compatible application wheels**, actually installed into
  `runtime/windows-x64/python/Lib/site-packages`. Windows `os_name`, `sys_platform`,
  machine, Python version and dependency-extra markers were evaluated explicitly;
  the Windows-only `colorama` dependency is included. No source distribution/compiler
  or Linux venv/node_modules was used as a Windows installation.
- Official pinned Windows **Node 22.23.4**, **MongoDB 8.0.34** and **Yarn 1.22.22**.
  The full vendor downloads were checksum-verified, then only runtime/license files
  retained. The 807,616,685-byte Mongo vendor ZIP/debug symbols are not in this bundle.
- **FFmpeg 9.0.2** from the Windows `imageio-ffmpeg==0.8.0` wheel. Its executable hash
  was also matched to upstream's pinned GyanD essentials release. License/build/source
  notices are retained separately from the Python wrapper's BSD license.
- An actual React production build from the updated source, made in an isolated
  frontend directory with local same-origin settings, not over the served build.

Public vendor URLs, fixed versions and the 50 wheel file checksums are recorded in
[`deploy/windows-prepared.json`](../deploy/windows-prepared.json). The generated
`runtime/windows-x64/bundle.json` adds every installed runtime/build file hash,
requirements/source fingerprints, public build settings and payload membership.
The ZIP's SHA256 is supplied **alongside** the ZIP, not embedded in itself.

## Compression is not another download/install

The genuine installed dependency file tree is compressed into
`runtime/windows-x64/installed-runtime.tar.xz` **inside the download**. Python's
standard library unpacks it on first launch; it does not need Windows 7-Zip, pip,
npm or internet for this step. The payload is approximately **85 MiB compressed /
375 MiB unpacked**, plus the base Python files, app/source/assets, build and normal
runtime data. Decoding uses a 32 MiB dictionary, not a multi-gigabyte dependency
resolver/build. First-run extraction time depends on the PC, disk and security scan.

Only manifest-listed runtime destinations are allowed. Archive paths, sizes,
duplicate members, symlinks and file hashes are checked before committing extracted
files. Modified known runtime files are preserved in `.cache/preserved-runtime-*`
before restoration. `.env`, database, media and arbitrary drive paths are not valid
payload destinations. Public assets shared by source and build are stored once and
copied into missing build paths locally. No app source/data is auto-replaced.

Later unchanged starts skip extraction, pip, frontend dependency installation and
builds. Stat/hash verification caching plus native version/import/FFmpeg checks
still detect missing/changed dependencies. A damaged local payload uses the safe
online fallback; `--repair` explicitly creates/reinstalls in a separate venv and
rebuilds. Both may need internet. Edited source/public configuration may require
real frontend dependency installation/build instead of the original shipped build.

## What was checked, and what was not

Checked in this workspace:

- Windows-aware locked/transitive package closure and compatible wheel targets.
- Real installed Windows files; static AMD64 PE/runtime DLL import-export metadata.
  Pip's unused cross-architecture launcher templates are resources, not app runtime
  executables. Expected operating-system DLLs still come from supported Windows.
- Official vendor archive checksums and the FFmpeg binary pin.
- Offline unpack/repair, path traversal/symlink/duplicate rejection, unchanged-start
  reuse, bounded discovery, no unnecessary pip/Yarn/build and data-preservation mocks.
- PowerShell fixtures for discovery, signatures/hashes, retry/error/reboot/UAC paths,
  Unicode/special-character arguments and real process exit-code forwarding.
- Separately compiled/intercepted browser checks: permitted/blocked autoplay, actual
  Enter/Space/touch gestures, sync, refreshed timer, intentional mute, Skip/Escape,
  responsive fit, reduced motion and the unchanged explicit 21+ consent gate.
  All API calls were mocked; external calls were blocked. No paid QA was repeated.

**Not checked:** actual Windows execution/Authenticode chain/UAC/CMD double-click/
default-browser behavior on a physical target PC, physical phone behavior, real
provider integration on a newly extracted folder, OAuth/webhooks/public deployment
or app-store/commercial/licensing approval. The workspace is Linux, not Windows.
The manual Windows fixture workflow remains owner-triggered and unexecuted here.

A prepared software bundle does not include the owner's private credentials,
customers, balances, history, purchases or generated media. Those remain private
and are never imported/reset by launch. Real service configuration and the separate
beta/production readiness gates remain necessary. Review the
[vendor license/source notices](WINDOWS_THIRD_PARTY.md) before public redistribution.
