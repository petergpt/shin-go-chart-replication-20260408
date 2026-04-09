# Repository License Notice

This repository is a mixed-rights research package.

## Original repository material

Unless otherwise noted, the original code and documentation added in this repository are made available under the MIT License:

```text
MIT License

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

This MIT grant covers the repository's original scripts, documentation, and packaging glue.

## Third-party and data exceptions

The MIT grant above does not override third-party terms on included or fetched data.

- `public_refs/go_learning_eras/`
  - copied public bridge data from `babeheim/go-learning-eras`
  - remains under upstream `CC BY-NC-SA 4.0`
- `osf/`
  - fetched locally from the Shin et al. public OSF project
  - not redistributed in git by this repository
  - remains subject to upstream terms
- `results/`
  - includes generated research outputs and committed review artifacts
  - no raw SGF files, game-level GoGoD records, or purchased archive payloads are included
  - `results/exact_replication/`
    - numerical reruns and comparison artifacts tied closely to the authors' public OSF release
    - no additional blanket repo-level license is asserted beyond the surrounding upstream context
  - `results/reverse_engineering/` and `results/paper_like_extension/`
    - original aggregate research outputs from this repository
    - released under `CC BY-NC-SA 4.0` as a conservative downstream policy for non-commercial reuse with attribution and share-alike terms

See [docs/DATA.md](docs/DATA.md) and [docs/PUBLIC_INPUT_MANIFEST.json](docs/PUBLIC_INPUT_MANIFEST.json) for the source boundaries and public-input provenance.
