<p align="center">
  <img src="docs/media/smb-camera-social.jpg" alt="SMB Camera" width="960">
</p>

<p align="center"><strong>Use your iPhone as a camera for Windows and OBS.</strong></p>

<p align="center">
  <a href="#beta"><img src="https://img.shields.io/badge/status-beta-b82f75?style=flat-square" alt="Beta candidate"></a>
  <a href="docs/INSTALL-WINDOWS.md"><img src="https://img.shields.io/badge/Windows-11%20x64-242a38?style=flat-square" alt="Windows 11 x64"></a>
  <a href="#beta"><img src="https://img.shields.io/badge/USB-1080p30-242a38?style=flat-square" alt="USB 1080p30"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-247056?style=flat-square" alt="MIT license"></a>
</p>

<p align="center">
  <a href="docs/INSTALL-WINDOWS.md"><strong>Windows setup</strong></a> ·
  <a href="docs/INSTALL-IOS.md">iPhone setup</a> ·
  <a href="docs/INSTALL-WINDOWS.md#obs-e-gravação">OBS setup</a> ·
  <a href="README.md">Português</a>
</p>

## What you can do

![SMB Camera desktop app showing a 1080p preview, a transparent background and sidebar recording controls](docs/media/smb-camera-desktop.jpg)

*Screenshot of the desktop app using a demonstration signal and a fictional subject.*

- **Control the camera from Windows.** Select lenses and adjust focus, zoom, exposure, framing, color and LUTs.
- **Use the SMB Camera source in OBS.** Use a transparent background, an image, a GIF, or a looping video with [optional NVIDIA background removal](docs/NVIDIA-BETA.md).
- **Record the original signal.** Save the incoming H.264 to MOV without re-encoding and optionally record the iPhone microphone.

## Beta

| Component | Tested reference |
| --- | --- |
| iPhone | SMB Camera 0.9 on iPhone 11 Pro Max with iOS 18.3.1 |
| PC | Desktop 0.19.1 on Windows 11 x64 with RTX 3060 Laptop |
| Video | 1080p30 SDR H.264 over USB |
| OBS | SMB Camera source with OBS x64 32.2.2 and OBS 33.0.0 Portable |
| Recording | MOV with original H.264 video and optional PCM audio |

The iPhone app requires [personal signing](docs/INSTALL-IOS.md). The beta focuses on the OBS source and original recording. The Windows virtual webcam is under development. Setup and contribution guides are currently in Portuguese.

[Contributing](CONTRIBUTING.md) · [Protocol](docs/PROTOCOL.md) · [Privacy](docs/PRIVACY.md) · [License](LICENSE)
