Vendored from https://github.com/johnfactotum/foliate-js
Commit: 78914aef4466eb960965702401634c2cb348e9b1 (2026-05-01)
Licence: MIT (see LICENSE). vendor/ keeps its own licences (pdf.js: Apache-2.0, zip.js: BSD-3-Clause, fflate: MIT).

One change from upstream: vendor/pdfjs/pdf.mjs and pdf.worker.mjs are the
LEGACY build of pdfjs-dist 5.5.207 (pdfjs-dist/legacy/build/), not the default
build foliate copies. The default build calls very new APIs
(Map.prototype.getOrInsertComputed, Math.sumPrecise, Promise.try, ...) and fails
on phone browsers such as Samsung Internet; the legacy build polyfills them.

To update: copy foliate's runtime .js files and vendor/ from a newer commit, then
replace the two pdf.js files with the legacy build of the matching pdfjs-dist version.
