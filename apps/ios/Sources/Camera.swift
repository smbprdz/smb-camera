import AVFoundation
import VideoToolbox
import Combine
import UIKit
import Network

final class Camera: NSObject, ObservableObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    @Published var status = "Pronto para ensaio 1080p30."
    @Published var inventory = "Capacidades ainda nao consultadas."
    @Published var isStreaming = false
    let queue = DispatchQueue(label:"ucs.media", qos:.userInitiated)
    let capture = AVCaptureSession()
    lazy var link: Link = {
        let value = Link(queue:queue)
        value.onMic = { [weak self] enabled in self?.setRecordingMic(enabled) }
        value.onReady = { [weak self] in self?.beginCapture() }
        value.onError = { [weak self] text in self?.stopOnQueue(text) }
        value.diagnostics = { [weak self] in self?.diagnostics() ?? [:] }
        value.onControl = { [weak self] command in self?.applyRemote(command) }
        value.onRTT = { [weak self] rtt in
            self?.publish(String(format:"Transmitindo. RTT %.2f ms (nao e latencia de camera).",rtt))
        }
        return value
    }()
    var micGeneration:UInt64 = 0
    var micInput:AVCaptureDeviceInput?
    var micOutput:AVCaptureAudioDataOutput?
    var micPending = 0
    var encoder: VTCompressionSession?
    var inFlight = 0
    var sequence: UInt64 = 0
    var epoch: UInt64 = 0
    var skipped = 0
    var mode:VideoMode = .fullHD
    var currentDevice:AVCaptureDevice?
    var capabilityRevision:UInt64=0
    var forceKeyframe=false
    var pendingRemote:RemoteCommand?
    var controlCache:[String:(RemoteCommand,[String:Any])]=[:]
    var controlOrder=[String]()
    private var usbBridge:USBBridge?
    private var unsupportedEncoderProperties=[String]()
    private var encodeTimes = [Double]()
    private var callbackAges = [Double]()
    private var encoderPolicy = "default"
    private func diagnostics() -> [String:Any] {
        func p95(_ values:[Double]) -> Double { let sorted=values.sorted(); return sorted.isEmpty ? 0 : sorted[Int(Double(sorted.count-1)*0.95)] }
        return ["encoder_p95_ms":p95(encodeTimes),"capture_callback_age_p95_ms":p95(callbackAges),
                "capture_skipped":skipped,"capture_callbacks":sequence,"thermal_state":ProcessInfo.processInfo.thermalState.rawValue,
                "encoder_policy":encoderPolicy,"unsupported_properties":unsupportedEncoderProperties]
    }
    private var observers: [NSObjectProtocol] = []
    override init() {
        super.init()
        for name in [AVCaptureSession.runtimeErrorNotification, AVCaptureSession.wasInterruptedNotification] {
            observers.append(NotificationCenter.default.addObserver(forName: name, object: capture, queue: nil) { [weak self] _ in
                self?.queue.async { [weak self] in self?.stopOnQueue("Captura interrompida pelo iOS. Reconecte quando estiver disponivel.") }
            })
        }
    }
    deinit { for observer in observers { NotificationCenter.default.removeObserver(observer) } }
    func publish(_ text:String) { DispatchQueue.main.async { self.status = text } }
    func start(host:String,pin:String,token:String,endpoint:NWEndpoint? = nil,mode:VideoMode = .fullHD,cable:Bool = false,allowMic:Bool = false) {
        AVCaptureDevice.requestAccess(for:.video) { allowed in
            self.queue.async {
                self.stopOnQueue("Conectando...")
                self.mode = mode
                guard allowed else { self.publish("Permissao de camera negada."); return }
                if cable {
                    let bridge = USBBridge(queue:self.queue)
                    self.usbBridge = bridge
                    bridge.onReady = { [weak self] port in
                        self?.link.open(host:"127.0.0.1",pin:pin,token:token,
                            endpoint:.hostPort(host:"127.0.0.1",port:NWEndpoint.Port(rawValue:port)!),mode:mode,allowMic:allowMic)
                    }
                    bridge.onError = { [weak self] text in self?.stopOnQueue(text) }
                    self.publish("Aguardando o PC pelo cabo USB. Mantenha este app aberto.")
                    bridge.start()
                } else { self.link.open(host:host,pin:pin,token:token,endpoint:endpoint,mode:mode,allowMic:allowMic) }
            }
        }
    }
    func stop() { queue.async { self.stopOnQueue("Parado.") } }
    func stopOnQueue(_ text:String) {
        epoch &+= 1
        setRecordingMic(false)
        link.close()
        usbBridge?.close();usbBridge=nil
        if capture.isRunning { capture.stopRunning() }
        if let encoder {
            VTCompressionSessionCompleteFrames(encoder,untilPresentationTimeStamp:.invalid)
            VTCompressionSessionInvalidate(encoder)
        }
        encoder = nil; inFlight = 0; sequence = 0; skipped = 0
        encodeTimes.removeAll(); callbackAges.removeAll()
        unsupportedEncoderProperties.removeAll()
        currentDevice=nil;capabilityRevision=0;pendingRemote=nil;controlCache.removeAll();controlOrder.removeAll();forceKeyframe=false
        DispatchQueue.main.async { self.isStreaming = false }
        publish(text)
    }
    func check(_ result: OSStatus,operation:String = "Encoder") throws {
        if result != noErr { throw EncoderConfigurationError(operation:operation,code:result) }
    }
    func beginCapture() {
        do {
            let devices = AVCaptureDevice.DiscoverySession(deviceTypes:[.builtInWideAngleCamera,
                .builtInUltraWideCamera,.builtInTelephotoCamera],mediaType:.video,position:.unspecified).devices
            let text = devices.map { device in
                let formats = device.formats.map { format -> String in
                    let d = CMVideoFormatDescriptionGetDimensions(format.formatDescription)
                    let ranges = format.videoSupportedFrameRateRanges.map { "\($0.minFrameRate)-\($0.maxFrameRate)" }.joined(separator:",")
                    return "\(d.width)x\(d.height) fps=\(ranges) HDR=\(format.isVideoHDRSupported) pixel=\(CMFormatDescriptionGetMediaSubType(format.formatDescription))"
                }.joined(separator:"; ")
                return "\(device.localizedName): \(formats)"
            }.joined(separator:"\n")
            DispatchQueue.main.async { self.inventory = text }
            guard let device = devices.first(where: { $0.position == .back && $0.deviceType == .builtInWideAngleCamera }),
                  let format = device.formats.first(where: {
                      let d = CMVideoFormatDescriptionGetDimensions($0.formatDescription)
                      return d.width == self.mode.width && d.height == self.mode.height && $0.supportedColorSpaces.contains(.sRGB) &&
                          $0.videoSupportedFrameRateRanges.contains(where: { $0.minFrameRate <= Double(self.mode.fps) && $0.maxFrameRate >= Double(self.mode.fps) })
                  }) else { stopOnQueue("\(mode.rawValue) SDR nao esta disponivel nesta camera. Escolha outro formato."); return }
            let input = try AVCaptureDeviceInput(device:device)
            capture.beginConfiguration()
            defer { capture.commitConfiguration() }
            capture.sessionPreset = .inputPriority
            for old in capture.inputs { capture.removeInput(old) }
            for old in capture.outputs { capture.removeOutput(old) }
            guard capture.canAddInput(input) else { throw NSError(domain:"CaptureInput",code:1) }
            capture.addInput(input)
            try device.lockForConfiguration()
            device.activeFormat = format
            device.activeVideoMinFrameDuration = CMTime(value:1,timescale:mode.fps)
            device.activeVideoMaxFrameDuration = CMTime(value:1,timescale:mode.fps)
            device.activeColorSpace = .sRGB
            device.automaticallyAdjustsVideoHDREnabled = false
            if format.isVideoHDRSupported { device.isVideoHDREnabled = false }
            device.unlockForConfiguration()
            currentDevice=device;capabilityRevision=1
            let output = AVCaptureVideoDataOutput()
            output.alwaysDiscardsLateVideoFrames = true
            output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange]
            output.setSampleBufferDelegate(self,queue:queue)
            guard capture.canAddOutput(output) else { throw NSError(domain:"CaptureOutput",code:1) }
            capture.addOutput(output)
            // Start from the working realtime encoder. Optional selectors/properties must not break capture.
            var specification: [CFString:Any] = [:]
            if #available(iOS 17.4, *) { specification[kVTVideoEncoderSpecification_RequireHardwareAcceleratedVideoEncoder] = true }
            let code = VTCompressionSessionCreate(allocator:kCFAllocatorDefault,width:mode.width,height:mode.height,
                codecType:kCMVideoCodecType_H264,encoderSpecification:specification as CFDictionary,imageBufferAttributes:nil,
                compressedDataAllocator:nil,outputCallback:nil,refcon:nil,compressionSessionOut:&encoder)
            encoderPolicy = "hardware-realtime"
            try check(code,operation:"Criar encoder \(mode.rawValue)")
            guard let encoder else { throw NSError(domain:"Encoder",code:1) }
            let props: [(CFString,CFTypeRef)] = [
                (kVTCompressionPropertyKey_RealTime,kCFBooleanTrue),
                (kVTCompressionPropertyKey_AllowFrameReordering,kCFBooleanFalse),
                (kVTCompressionPropertyKey_ProfileLevel,kVTProfileLevel_H264_High_AutoLevel),
                (kVTCompressionPropertyKey_AverageBitRate,NSNumber(value:mode.bitrate))]
            for (key,value) in props { try check(VTSessionSetProperty(encoder,key:key,value:value),operation:key as String) }
            let optional: [(CFString,CFTypeRef)] = [
                (kVTCompressionPropertyKey_ExpectedFrameRate,NSNumber(value:mode.fps)),
                (kVTCompressionPropertyKey_MaxKeyFrameInterval,NSNumber(value:mode.fps)),
                (kVTCompressionPropertyKey_MaxFrameDelayCount,NSNumber(value:1)),
                (kVTCompressionPropertyKey_ColorPrimaries,kCVImageBufferColorPrimaries_ITU_R_709_2),
                (kVTCompressionPropertyKey_TransferFunction,kCVImageBufferTransferFunction_ITU_R_709_2),
                (kVTCompressionPropertyKey_YCbCrMatrix,kCVImageBufferYCbCrMatrix_ITU_R_709_2)]
            for (key,value) in optional {
                let status = VTSessionSetProperty(encoder,key:key,value:value)
                if status != noErr { unsupportedEncoderProperties.append("\(key):\(status)") }
            }
            // Keep colour metadata on the source pixel buffers; some encoders do not expose these VT properties.
            try check(VTCompressionSessionPrepareToEncodeFrames(encoder))
            let generation = epoch
            queue.async { [weak self] in
                guard let self, self.epoch == generation, self.link.ready else { return }
                self.capture.startRunning()
                guard self.capture.isRunning else { self.stopOnQueue("Camera nao iniciou."); return }
                DispatchQueue.main.async { self.isStreaming = true }
                self.publish("Transmitindo \(self.mode.rawValue) H.264 SDR.")
                self.sendCapabilities()
            }
        } catch { stopOnQueue("Falha de captura/encoder: \(error.localizedDescription)") }
    }
    func captureOutput(_ output:AVCaptureOutput, didOutput sampleBuffer:CMSampleBuffer, from connection:AVCaptureConnection) {
        if output is AVCaptureAudioDataOutput {
            if output === micOutput { sendRecordingAudio(sampleBuffer) }; return
        }
        let seq = sequence; sequence &+= 1
        guard link.ready, let encoder, let image = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        guard CVPixelBufferGetWidth(image) == Int(mode.width), CVPixelBufferGetHeight(image) == Int(mode.height) else {
            stopOnQueue("Formato capturado difere de \(mode.rawValue). Escolha outro modo."); return
        }
        guard inFlight < 3 else { skipped += 1; return } // Drop before encode to preserve GOP references.
        inFlight += 1
        let generation = epoch
        let pts = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        let encodeStart = DispatchTime.now().uptimeNanoseconds
        let captureAgeMs = Double(encodeStart)/1_000_000-CMTimeGetSeconds(pts)*1000
        if captureAgeMs >= 0 && captureAgeMs < 60_000 {
            callbackAges.append(captureAgeMs)
            if callbackAges.count > 120 { callbackAges.removeFirst() }
        }
        let properties:CFDictionary? = forceKeyframe ? [kVTEncodeFrameOptionKey_ForceKeyFrame:true] as CFDictionary : nil
        forceKeyframe=false
        let code = VTCompressionSessionEncodeFrame(encoder,imageBuffer:image,presentationTimeStamp:pts,
            duration:CMTime(value:1,timescale:mode.fps),frameProperties:properties,infoFlagsOut:nil) { [weak self] status, flags, encoded in
                guard let self else { return }
                let callbackTime = DispatchTime.now().uptimeNanoseconds
                self.queue.async {
                    guard self.epoch == generation else { return }
                    self.encodeTimes.append(Double(callbackTime-encodeStart)/1_000_000)
                    if self.encodeTimes.count > 120 { self.encodeTimes.removeFirst() }
                    guard status == noErr, !flags.contains(.frameDropped), let encoded,
                          let data = Self.annexB(encoded) else {
                        self.stopOnQueue("Encoder descartou/falhou; reinicie a transmissao."); return
                    }
                    let attachments = CMSampleBufferGetSampleAttachmentsArray(encoded,createIfNecessary:false) as? [[CFString:Any]]
                    let key = (attachments?.first?[kCMSampleAttachmentKey_NotSync] as? Bool) != true
                    let micros = UInt64(max(0,CMTimeGetSeconds(pts)*1_000_000))
                    guard data.count <= 4*1024*1024 else { self.stopOnQueue("Frame excedeu limite de transporte."); return }
                    self.link.send(Wire.packet(3,data,seq:seq,pts:micros,key:key)) { self.inFlight -= 1 }
                }
            }
        if code != noErr { stopOnQueue("VideoToolbox encode retornou \(code).") }
    }
    static func annexB(_ sample:CMSampleBuffer) -> Data? {
        guard let format = CMSampleBufferGetFormatDescription(sample), let block = CMSampleBufferGetDataBuffer(sample) else { return nil }
        var result = Data(); let start = Data([0,0,0,1])
        var nalHeader: Int32 = 0
        for index in 0..<2 {
            var pointer: UnsafePointer<UInt8>?; var length = 0; var count = 0
            guard CMVideoFormatDescriptionGetH264ParameterSetAtIndex(format,parameterSetIndex:index,
                parameterSetPointerOut:&pointer,parameterSetSizeOut:&length,parameterSetCountOut:&count,
                nalUnitHeaderLengthOut:&nalHeader) == noErr, let pointer else { return nil }
            result.append(start); result.append(pointer,count:length)
        }
        guard nalHeader == 4 else { return nil }
        var bytes = Data(count:CMBlockBufferGetDataLength(block))
        let code = bytes.withUnsafeMutableBytes { raw in
            CMBlockBufferCopyDataBytes(block,atOffset:0,dataLength:raw.count,destination:raw.baseAddress!)
        }
        guard code == noErr else { return nil }
        var offset = 0
        while offset+4 <= bytes.count {
            let n = Int(Wire.number(bytes,offset,4)); offset += 4
            guard n>0, offset+n <= bytes.count else { return nil }
            result.append(start); result.append(bytes.subdata(in:offset..<(offset+n))); offset += n
        }
        return offset == bytes.count ? result : nil
    }
}
