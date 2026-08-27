# Submission profiles

Read this file only for a named venue, manuscript submission, camera-ready delivery, or venue compliance review. The machine-readable values are in `submission_profiles.json`.

## Status and interpretation

All profiles were checked on 2026-08-27 against the official sources listed below. They are project-owned submission profiles. They are not publisher-supplied artwork, official brand templates, or evidence that a figure will pass editorial or production checks.

The renderer creates PDF, SVG, and PNG working artifacts for reproducibility. A profile's `submission_formats` records what its cited guidance accepts; do not assume that every generated working artifact is an accepted final-submission file.

Values marked “project default” make a useful deterministic canvas where an official guide leaves the choice to the author or typesetter. Values marked “recheck” were either variable across publications or not fully retrievable by automated access. The exact target publication always wins.

## Nature Portfolio

Use `nature-portfolio` for the flagship `Nature` figure workflow, then check the selected Nature Portfolio journal.

Official guidance checked:

- [Initial submission | Nature](https://www.nature.com/nature/for-authors/initial-submission)
- [Final submission | Nature](https://www.nature.com/nature/for-authors/final-submission)
- [Building and exporting figure panels | Nature research figure guide](https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/)
- [Preparing figures to our specifications | Nature research figure guide](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/)

The current guide specifies 89 mm and 183 mm printed widths, a 170 mm maximum figure height,
5–7 pt editable text, standard sans-serif fonts such as Arial or Helvetica, and accessible colors.
It recommends editable vector artwork for graphs. Raster-resolution wording differs by artwork
class and submission stage: the guide discusses 300 dpi Extended Data and photographic material,
while its main-figure export guidance prefers vector files and contains higher raster-quality
wording elsewhere. The profile therefore emits a 300 dpi PNG as a reproducible working preview,
not as an asserted official minimum for every `Nature` figure. The final-submission page also gives
a 120–136 mm intermediate width. Heights below 170 mm in the config are project defaults, not
mandated aspect ratios.

Variable items: journal, article type, production stage, editable-layer requirement, and production resizing.

## Science/AAAS

Use `science-aaas` only for the flagship `Science` workflow. Do not apply it to Science Partner Journals or assume it covers every Science family title.

Official pages checked:

- [Instructions for preparing an initial manuscript | Science](https://www.science.org/content/page/instructions-preparing-initial-manuscript)
- [Instructions for authors of revised research articles | Science](https://www.science.org/content/page/instructions-authors-revised-research-articles)

Both official URLs were discoverable on 2026-08-27 but returned HTTP 403 to automated retrieval. The profile's widths, heights, font range, and 300 dpi export are therefore conservative project working defaults, not asserted current Science numerical rules. Reopen both pages in a normal browser and confirm current widths, accepted formats, resolution, font, and initial-versus-revised rules before submission.

Variable items: initial versus revised submission, exact Science family journal, production source request, and current layout.

## IEEE

Use `ieee` for general IEEE journal graphics, then check the specific publication.

Official guidance checked:

- [Resolution and Size | IEEE Author Center Journals](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/resolution-and-size/)
- [File Formatting | IEEE Author Center Journals](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/file-formatting/)
- [Create Graphics for Your Article | IEEE Author Center Journals](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/)

The current Author Center gives 88.9 mm/3.5 in and 182 mm/7.16 in widths, more than 300 dpi for color or grayscale non-vector graphics, more than 600 dpi for black-and-white line art, a maximum 220 mm/8.8 in file height, accepted PS/EPS/PDF/PNG/TIFF formats, embedded fonts, and type appearing around 9–10 pt at full size. It explicitly recommends redundant color plus shape/line encoding for accessibility. The configured chart PNG uses 600 dpi because plots are line art; `--dpi 300` remains available for a color/grayscale raster use case.

Variable items: journal or conference, Proceedings of the IEEE's documented column exception, raster artwork class, and final template.

## ACM

Use `acm` as a TAPS-oriented starting point, then inspect the conference or journal instructions and the generated TAPS proofs.

Official guidance checked:

- [Submission Template for ACM Papers](https://authors.acm.org/binaries/content/assets/publications/taps/acm_layout_submission_template.pdf)
- [Best Practices for Submitting the LaTeX](https://authors.acm.org/binaries/content/assets/publications/taps/latex-best_practices-06-may-2020.pdf)
- [ACM Primary Article Template Instructions](https://www.acm.org/binaries/content/assets/publications/taps/acm_primary_article_template_instructions.pdf)
- [Describing Figures for ACM Publications](https://www.acm.org/publications/taps/describing-figures/)

The current primary-template material distinguishes half-width and full-width figures, requires figures to remain usable in grayscale through redundant patterns/lines/shapes, and requires descriptions for meaningful figures. LaTeX guidance uses `figure` for one-column and `figure*` for full-width output. Exact column widths, raster resolution, and fonts vary with the selected ACM layout, so 84.5 mm, 177.8 mm, 300 dpi, and the font range are project defaults. Meaningful alt text is part of the package regardless of target.

Variable items: publication, TAPS layout, review versus production format, exact dimensions, image-resolution instructions, and accessibility checklist.

## Override safely

Use spec-level `width_mm`, `height_mm`, `dpi`, `font_family`, or `font_size_pt` only when the exact venue instructions or editor request justify the override. The manifest records the resolved values and the profile hash. Keep a note in the caption or task record when an override affects interpretation or legibility.
