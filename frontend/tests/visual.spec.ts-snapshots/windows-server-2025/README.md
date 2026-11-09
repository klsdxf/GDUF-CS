# Windows Server 2025 visual baselines

These 32 reviewed snapshots are specific to GitHub's Windows Server 2025 / windows-2025-vs2026 image with Edge, not the desktop Windows font environment. Source: run 42648503733, commit a65f89bead7dca1ecaf5c718761d05100634ea7c. They were extracted from that run's actual screenshots, compared with the desktop references and reviewed as paired full-page contact sheets. The product DOM/CSS was identical; glyph rasterization/metrics and consequent text wrapping differed (maximum full-page height difference 22 px). PNG optimization is lossless.

The original desktop snapshots remain unchanged. `VISUAL_BASELINE_PLATFORM=windows-server-2025` selects this set explicitly in CI. Tests keep the 0.1% pixel comparison threshold and still fail on layout/content regressions within the same environment. No automatic baseline updates run in CI. Other platform identifiers fail configuration rather than silently choosing an unrelated baseline.

V6 result-page verification continues to compare the live page directly with the immutable frozen HTML in the same browser/environment at all 14 widths; this platform selection does not affect that check. The full context and measurements are in reports/results-v6/ci-font-environment-differences.json.
