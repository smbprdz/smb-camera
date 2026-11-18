import AVFoundation
import AudioToolbox
import Foundation

extension Camera: AVCaptureAudioDataOutputSampleBufferDelegate {
    // All capture configuration and callbacks run on the existing media queue.
    func setRecordingMic(_ enabled: Bool) {
        micGeneration &+= 1
        let generation = micGeneration
        micPending = 0
        if !enabled {
            if let input = micInput, let output = micOutput {
                capture.beginConfiguration()
                output.setSampleBufferDelegate(nil, queue:nil)
                capture.removeOutput(output)
                capture.removeInput(input)
                capture.commitConfiguration()
            }
            micInput = nil
            micOutput = nil
            return
        }
        guard micInput == nil else { return }
        AVCaptureDevice.requestAccess(for:.audio) { [weak self] granted in
            self?.queue.async { [weak self] in
                guard let self, self.micGeneration == generation, self.link.ready else { return }
                guard granted, let device = AVCaptureDevice.default(for:.audio),
                      let input = try? AVCaptureDeviceInput(device:device) else {
                    self.micUnavailable()
                    return
                }
                let output = AVCaptureAudioDataOutput()
                self.capture.beginConfiguration()
                guard self.capture.canAddInput(input) else {
                    self.capture.commitConfiguration()
                    self.micUnavailable()
                    return
                }
                self.capture.addInput(input)
                guard self.capture.canAddOutput(output) else {
                    self.capture.removeInput(input)
                    self.capture.commitConfiguration()
                    self.micUnavailable()
                    return
                }
                self.capture.addOutput(output)
                output.setSampleBufferDelegate(self, queue:self.queue)
                self.micInput = input
                self.micOutput = output
                self.capture.commitConfiguration()
                self.forceKeyframe = true
            }
        }
    }

    private func micUnavailable() {
        setRecordingMic(false)
        link.send(Wire.packet(12)) {}
        publish("Microfone indisponível para a gravação. O vídeo continua ativo.")
    }

    func sendRecordingAudio(_ sample: CMSampleBuffer) {
        guard let description = CMSampleBufferGetFormatDescription(sample),
              let format = CMAudioFormatDescriptionGetStreamBasicDescription(description)?.pointee,
              let block = CMSampleBufferGetDataBuffer(sample) else { micUnavailable(); return }
        let flags = format.mFormatFlags
        let channels = format.mChannelsPerFrame
        let size = CMBlockBufferGetDataLength(block)
        let pts = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sample))
        let integer = format.mBitsPerChannel == 16 && flags & kAudioFormatFlagIsSignedInteger != 0
        let floating = format.mBitsPerChannel == 32 && flags & kAudioFormatFlagIsFloat != 0
        let bytesPerSample = Int(format.mBitsPerChannel / 8)
        let frames = CMSampleBufferGetNumSamples(sample)
        guard format.mFormatID == kAudioFormatLinearPCM, integer || floating,
              flags & kAudioFormatFlagIsBigEndian == 0,
              (channels == 1 || (channels == 2 && flags & kAudioFormatFlagIsNonInterleaved == 0)),
              Int(format.mBytesPerFrame) == Int(channels) * bytesPerSample,
              format.mSampleRate == 44100 || format.mSampleRate == 48000,
              (1...16382).contains(frames), size == frames * Int(channels) * bytesPerSample,
              pts.isFinite, pts >= 0, micPending < 8 else { micUnavailable(); return }
        var payload = Data()
        Wire.append(UInt32(format.mSampleRate), to:&payload)
        Wire.append(UInt16(channels), to:&payload)
        if integer {
            payload.count += size
            let result = payload.withUnsafeMutableBytes { (raw: UnsafeMutableRawBufferPointer) in
                CMBlockBufferCopyDataBytes(block, atOffset:0, dataLength:size, destination:raw.baseAddress!.advanced(by:6))
            }
            guard result == noErr else { micUnavailable(); return }
        } else {
            var samples = [Float](repeating:0, count:frames * Int(channels))
            let result = samples.withUnsafeMutableBytes { raw in
                CMBlockBufferCopyDataBytes(block, atOffset:0, dataLength:size, destination:raw.baseAddress!)
            }
            guard result == noErr else { micUnavailable(); return }
            let pcm = samples.map { value -> Int16 in
                let clipped = value.isFinite ? max(-1, min(1, value)) : 0
                return Int16(clamping:Int((clipped * 32768).rounded())).littleEndian
            }
            pcm.withUnsafeBytes { payload.append(contentsOf:$0) }
        }
        let generation = micGeneration
        micPending += 1
        link.send(Wire.packet(10,payload,pts:UInt64(pts * 1_000_000))) { [weak self] in
            guard let self, generation == self.micGeneration else { return }
            self.micPending -= 1
        }
    }
}
