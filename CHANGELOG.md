# Changelog

All notable changes to pymmich are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-04-19

### Added

- GitHub Actions workflow that builds the Zensical documentation site
  and deploys it to GitHub Pages on every push to `main`.
- GitHub Actions release workflow triggered by `v*` tags that builds
  sdist + wheel and PyInstaller one-file binaries for Linux, Windows,
  and macOS (Apple Silicon), then attaches them to a GitHub Release.
- Hosted documentation at <https://malemburg.github.io/pymmich/>,
  linked from the README.

### Changed

- The `Documentation` URL in `pyproject.toml` now points to the hosted
  Zensical site instead of the GitHub repository.

## [0.2.0] - 2026-04-19

### Added

- `upload --album/-a NAME` routes every input (standalone files and all
  files found in directories) into a single target album instead of
  creating one album per directory.
- `upload --force/-f` allows reusing filenames already present on the
  server. Without `--force`, colliding filenames are renamed with a
  numbered suffix (`foo.jpg` → `foo_1.jpg`) and a warning is printed.
- `download --force/-f` overwrites pre-existing local files. Without
  `--force`, colliding filenames are saved as `foo.jpg` → `foo_1.jpg`
  and a warning is printed.
- `just publish` and `just publish-test` targets for releasing to PyPI
  and TestPyPI.

### Changed

- Recursive uploads (`upload -r`) now explicitly place every file found
  under a directory into that directory's album, documented in the spec.
- GitHub URLs in `pyproject.toml` and the docs point to
  `github.com/malemburg/pymmich`.

## [0.1.0] - 2026-04-18

### Added

- Initial release of pymmich: CLI for uploading and downloading photos
  and videos to/from an Immich server.
- Commands: `upload`, `download`, `share`, `unshare`, `list`,
  `list-users`.
- PyPI-ready build (sdist + wheel) and optional PyInstaller one-file
  binary.
- Zensical-generated documentation site.
