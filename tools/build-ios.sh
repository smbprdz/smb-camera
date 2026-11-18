#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 tools/generate_xcode.py
xcodebuild -version
xcrun swiftc apps/ios/Sources/Wire.swift apps/ios/Sources/PairingRecord.swift apps/ios/Sources/StreamTiming.swift apps/ios/Sources/VideoMode.swift apps/ios/Sources/RemoteCommand.swift tests/swift/main.swift -o /tmp/ucs-wire-tests
/tmp/ucs-wire-tests
xcodebuild -project apps/ios/UniversalCamera.xcodeproj -scheme UniversalCamera \
  -configuration Release -sdk iphoneos -destination 'generic/platform=iOS' \
  -derivedDataPath build/ios CODE_SIGNING_ALLOWED=NO build
mkdir -p build/unsigned/Payload
ditto build/ios/Build/Products/Release-iphoneos/UniversalCamera.app build/unsigned/Payload/UniversalCamera.app
(cd build/unsigned && zip -qr UniversalCamera-unsigned.ipa Payload)
shasum -a 256 build/unsigned/UniversalCamera-unsigned.ipa
echo 'Unsigned IPA: requires legitimate signing/provisioning before installation.'
