# Windows bundle: third-party licenses and source pointers

The prepared download includes third-party software, not an exclusively app-owned
binary distribution. Versions/checksums are in
[`deploy/windows-prepared.json`](../deploy/windows-prepared.json). Keep the original
copyright/license notices. Inclusion here is not a representation of store approval,
a security warranty or clearance of every commercial/public redistribution use.
Review applicable obligations before publishing or distributing a modified release.

## Python and Python packages

- **CPython / PSF NuGet 3.13.16:** original license at
  `runtime/windows-x64/python/LICENSE.txt`. Source/release information:
  https://www.python.org/downloads/release/python-31316/ and
  https://github.com/python/cpython/tree/v3.13.16 .
- The installed packages retain their `.dist-info` metadata and vendor-provided
  license directories under `runtime/windows-x64/python/Lib/site-packages` after
  offline unpacking. The manifest lists the exact 50 application packages; pip is
  additionally supplied with the official Python runtime. Package/source links:
  https://pypi.org/ (use each manifest package name/version), and vendor metadata.
- No Linux shared libraries or cross-pip Linux console stubs are shipped as Windows
  runtime programs. Pip's original unused x86/ARM launcher templates remain tools'
  resources; the application runtime is Windows AMD64.

## Node.js and Yarn

- **Node 22.23.4:** `runtime/windows-x64/node/LICENSE` (including its bundled notices).
  Release/source: https://nodejs.org/dist/v22.23.4/ and
  https://github.com/nodejs/node/tree/v22.23.4 .
- **Yarn 1.22.22:** original package license in `runtime/windows-x64/yarn/`.
  Source: https://github.com/yarnpkg/yarn/tree/v1.22.22 .
- The compiled React build retains the generated third-party license notices in
  `frontend/build/static/js/`; dependency source/version information is in
  `frontend/package.json` and `frontend/yarn.lock`. Production compilation does not
  replace those upstream licenses with the application's own terms.

## MongoDB and Microsoft runtime

- **MongoDB Community 8.0.34:**
  `runtime/windows-x64/mongodb/LICENSE-Community.txt` (**SSPL v1**) and
  `runtime/windows-x64/mongodb/THIRD-PARTY-NOTICES` are retained from the official
  vendor ZIP. Exact source/release tree: https://github.com/mongodb/mongo/tree/r8.0.34 .
  SSPL obligations, especially offering MongoDB functionality as a service, must be
  assessed separately before public hosting/redistribution. This launcher is not
  a new hosted database service or cloud migration.
- **Microsoft Visual C++ runtime DLLs:** original signed x64 runtime files were
  extracted from the redistributable included in the pinned official MongoDB ZIP;
  they sit beside `mongod.exe` as app-local prerequisites. Original license terms:
  `runtime/windows-x64/mongodb/MICROSOFT-LICENSE.rtf`. Microsoft redistribution rules:
  https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files .
  Windows/UCRT/system DLLs are not copied from this Linux host or supplied as an OS.

## FFmpeg — separate from the Python wrapper license

- **imageio-ffmpeg 0.8.0** is a BSD-licensed Python wrapper. That does **not** make
  the FFmpeg executable BSD-licensed.
- Included binary: **FFmpeg 9.0.2 Windows x86_64 GyanD essentials**, unchanged from
  the official Windows wheel. The matching upstream archive:
  https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip .
  The archive/binary SHA256 values are recorded in the public vendor manifest.
- Retained upstream [GPL license](licenses/FFmpeg-9.0.2-LICENSE) and
  [build/configuration/dependency/source README](licenses/FFmpeg-9.0.2-README.txt).
  These are upstream files, not newly written licenses. FFmpeg source/releases:
  https://ffmpeg.org/download.html and https://ffmpeg.org/releases/ .
  Builder/source/dependency information: https://www.gyan.dev/ffmpeg/builds/ and
  https://github.com/GyanD/codexffmpeg . The upstream README identifies the actual
  configure options and linked components; retain the corresponding source/build
  materials and satisfy the applicable GPL/source-access obligations when publishing.
- Imageio's exact binary provenance pins and download/build helper:
  https://github.com/imageio/imageio-ffmpeg/blob/v0.8.0/tools/ffmpeg-sources.json .
  Additional licensing guidance: https://ffmpeg.org/legal.html .

These pointers are not permission to omit source/notice obligations in a public
release. Maintain corresponding source availability for the exact binaries you
redistribute and review any platform/store restrictions. No app-store licensing or
production-readiness certification was performed by building this local download.
