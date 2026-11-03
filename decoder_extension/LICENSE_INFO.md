# Licensing and provenance

The upstream WSJT-X 3.0.2 `lib/wsprd/wsprd.c` identifies Joe Taylor, K1JT (copyright 2001–2018) and Steven Franke, K9AN (copyright 2014–2018), and states GNU GPL version 3 or later. Its `fano.c` credits Phil Karn, KA9Q, with modifications by Joe Taylor. The patches in `patches/` modify those upstream sources and must be treated as GPL-covered derivative work, not as MIT-licensed code. [COPYING.GPL-3](COPYING.GPL-3) supplies the GPL version 3 text. The unmodified upstream notices remain in the source to which patches apply.

The full corresponding source can be obtained by applying the patches to the pinned [official 3.0.2 source archive](https://github.com/WSJTX/wsjtx/releases/download/v3.0.2/wsjtx-3.0.2-src.tar.gz); `build.sh` performs this operation and checks the archive SHA-256. The repository does not redistribute WSJT-X binaries or its complete source archive. Follow the upstream license terms when redistributing a modified binary or source.

Project-authored Python analysis, build orchestration, documentation and input-generation code outside the derivative patches are distributed under the repository's [MIT license](../LICENSE), except that generated and modified upstream decoder code remains GPL-covered. Result tables follow [CC BY 4.0](../LICENSE-DATA). No endorsement by the WSJT-X authors is implied.
