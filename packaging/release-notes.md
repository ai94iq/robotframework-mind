## Desktop bundles

Download the file for your system, then start it. No Python needed.

| System | File |
|---|---|
| Windows 10 or 11, x64 | `robotframework-mind-<version>-windows-x64.exe` |
| Windows 10 or 11, x64 (installer with Start menu shortcut) | `robotframework-mind-<version>-windows-x64-setup.exe` |
| Linux x64 (glibc 2.39 or newer, such as Ubuntu 24.04) | `robotframework-mind-<version>-linux-x64.tar.gz` |
| macOS on Apple silicon | `robotframework-mind-<version>-macos-arm64.dmg` |
| macOS on Intel | `robotframework-mind-<version>-macos-x64.dmg` |

On Linux, Qt needs the system's X11 or Wayland libraries (Debian and Ubuntu: `libxcb-cursor0`).

**The bundles are not signed yet**, so the system warns the first time:

- Windows: SmartScreen says it protected your PC; choose More info, then Run anyway. Antivirus software sometimes
  flags single-file Python apps; compare the file with `SHA256SUMS` before running it.
- macOS: right-click the app and choose Open, or run `xattr -dr com.apple.quarantine robotframework-mind.app`.

**Licenses**: the bundles ship Qt (PySide6, LGPL-3.0) and Robot Framework (Apache-2.0); every license text is in
the bundle's `licenses` folder.
