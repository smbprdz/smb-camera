import AVFoundation
import Foundation

extension Camera {
    func cameraDevices() -> [AVCaptureDevice] {
        AVCaptureDevice.DiscoverySession(deviceTypes:[.builtInWideAngleCamera,.builtInUltraWideCamera,.builtInTelephotoCamera],
            mediaType:.video,position:.unspecified).devices
    }
    func captureFormat(_ device:AVCaptureDevice) -> AVCaptureDevice.Format? {
        device.formats.first {
            let d=CMVideoFormatDescriptionGetDimensions($0.formatDescription)
            return d.width==mode.width && d.height==mode.height && $0.supportedColorSpaces.contains(.sRGB) &&
                $0.videoSupportedFrameRateRanges.contains(where:{ $0.minFrameRate<=Double(mode.fps) && $0.maxFrameRate>=Double(mode.fps) })
        }
    }
    func zoomLimits(_ device:AVCaptureDevice) -> (Double,Double) {
        (max(1,Double(device.minAvailableVideoZoomFactor)),min(Double(device.maxAvailableVideoZoomFactor),Double(device.activeFormat.videoMaxZoomFactor)))
    }
    func deviceState(_ device:AVCaptureDevice) -> [String:Any] {
        let autoSupported=device.isFocusModeSupported(.continuousAutoFocus) || device.isFocusModeSupported(.autoFocus)
        let manualSupported=device.isLockingFocusWithCustomLensPositionSupported && device.isFocusModeSupported(.locked)
        let focusMode=(!autoSupported && !manualSupported) ? "fixed" : device.focusMode == .locked ? "manual" : "auto"
        var state:[String:Any] = ["zoom":Double(device.videoZoomFactor),"focus":Double(device.lensPosition),"focus_mode":focusMode]
        if exposureLimits(device) != nil {
            state["exposure_bias"]=Double(device.exposureTargetBias)
            let iso=Double(device.iso),duration=CMTimeGetSeconds(device.exposureDuration)*1_000_000
            if iso.isFinite,iso>0,iso<=1_000_000 { state["sensor_iso"]=iso }
            if duration.isFinite,duration>0,duration<=1_000_000_000 { state["sensor_exposure_us"]=duration }
        }
        return state
    }
    func exposureLimits(_ device:AVCaptureDevice) -> [String:Any]? {
        let low=Double(device.minExposureTargetBias),high=Double(device.maxExposureTargetBias),value=Double(device.exposureTargetBias)
        guard device.isExposureModeSupported(.continuousAutoExposure) || device.isExposureModeSupported(.autoExpose),
              low.isFinite,high.isFinite,value.isFinite,low>=(-128),high<=128,low<=high,value>=low,value<=high else { return nil }
        return ["min":low,"max":high]
    }
    func sendCapabilities() {
        guard let device=currentDevice,let session=link.controlSession else { return }
        let limits=zoomLimits(device)
        let cameras:[[String:Any]]=cameraDevices().map { camera in
            let side=camera.position == .front ? "Frontal" : "Traseira"
            let lens=camera.deviceType == .builtInUltraWideCamera ? "Ultra grande-angular" : camera.deviceType == .builtInTelephotoCamera ? "Teleobjetiva" : "Principal"
            return ["id":camera.uniqueID,"label":"\(side): \(lens)","available":captureFormat(camera) != nil]
        }
        var payload:[String:Any] = ["session":session,"revision":capabilityRevision,"active":device.uniqueID,"cameras":cameras,
            "zoom_min":limits.0,"zoom_max":limits.1,
            "focus_auto_supported":device.isFocusModeSupported(.continuousAutoFocus) || device.isFocusModeSupported(.autoFocus),
            "focus_manual_supported":device.isLockingFocusWithCustomLensPositionSupported && device.isFocusModeSupported(.locked),
            "state":deviceState(device)]
        if let exposure=exposureLimits(device) { payload["exposure_bias"]=exposure }
        link.sendControlJSON(7,payload)
    }
    func replyRemote(_ command:RemoteCommand,status:String,reason:String? = nil,cache:Bool = true) {
        guard let session=link.controlSession else { return }
        var result:[String:Any]=["session":session,"revision":capabilityRevision,"request":command.request,"status":status]
        if let reason { result["reason"]=reason }
        if let device=currentDevice { result["active"]=device.uniqueID;result["state"]=deviceState(device) }
        if cache {
            controlCache[command.request]=(command,result);controlOrder.append(command.request)
            if controlOrder.count>32 { controlCache.removeValue(forKey:controlOrder.removeFirst()) }
        }
        if pendingRemote?.request==command.request { pendingRemote=nil }
        link.sendControlJSON(9,result)
    }
    func applyRemote(_ command:RemoteCommand) {
        guard let device=currentDevice,let session=link.controlSession,link.ready else { return }
        if command.session != session { replyRemote(command,status:"rejected",reason:"stale_session",cache:false);return }
        if let (cachedCommand,result)=controlCache[command.request] {
            if cachedCommand==command { link.sendControlJSON(9,result) }
            else { replyRemote(command,status:"rejected",reason:"request_id_reused",cache:false) }
            return
        }
        if let pending=pendingRemote,pending.request==command.request {
            if pending==command { return }
            link.onError?("Identificador de comando reutilizado com outro valor.");return
        }
        guard pendingRemote==nil else { replyRemote(command,status:"rejected",reason:"busy");return }
        guard command.revision==capabilityRevision else { replyRemote(command,status:"rejected",reason:"stale_revision");return }
        pendingRemote=command
        do {
            switch (command.control,command.value) {
            case ("exposure_bias",.number(let bias)):
                guard exposureLimits(device) != nil,bias>=Double(device.minExposureTargetBias),bias<=Double(device.maxExposureTargetBias) else {
                    replyRemote(command,status:"rejected",reason:"range");return
                }
                let generation=epoch
                try device.lockForConfiguration()
                device.exposureMode=device.isExposureModeSupported(.continuousAutoExposure) ? .continuousAutoExposure : .autoExpose
                device.setExposureTargetBias(Float(bias)) { [weak self] _ in
                    self?.queue.async { [weak self] in
                        guard let self,self.epoch==generation,self.currentDevice?.uniqueID==device.uniqueID,
                              self.pendingRemote?.request==command.request else { return }
                        self.replyRemote(command,status:"applied")
                    }
                }
                device.unlockForConfiguration()
                queue.asyncAfter(deadline:.now()+4) { [weak self] in
                    guard let self,self.epoch==generation,self.pendingRemote?.request==command.request else { return }
                    self.replyRemote(command,status:"rejected",reason:"failed")
                }
                return
            case ("zoom",.number(let zoom)):
                let limits=zoomLimits(device)
                guard zoom>=limits.0,zoom<=limits.1 else { replyRemote(command,status:"rejected",reason:"range");return }
                try device.lockForConfiguration()
                device.videoZoomFactor=CGFloat(zoom)
                device.unlockForConfiguration()
            case ("focus",.text("auto")):
                let target:AVCaptureDevice.FocusMode = device.isFocusModeSupported(.continuousAutoFocus) ? .continuousAutoFocus : .autoFocus
                guard device.isFocusModeSupported(target) else { replyRemote(command,status:"rejected",reason:"unsupported");return }
                try device.lockForConfiguration();device.focusMode=target;device.unlockForConfiguration()
            case ("focus",.number(let focus)):
                guard device.isLockingFocusWithCustomLensPositionSupported,device.isFocusModeSupported(.locked) else {
                    replyRemote(command,status:"rejected",reason:"unsupported");return
                }
                let generation=epoch
                try device.lockForConfiguration()
                device.setFocusModeLocked(lensPosition:Float(focus)) { [weak self] _ in
                    self?.queue.async { [weak self] in
                        guard let self,self.epoch==generation,self.currentDevice?.uniqueID==device.uniqueID,
                              self.pendingRemote?.request==command.request else { return }
                        self.replyRemote(command,status:"applied")
                    }
                }
                device.unlockForConfiguration()
                queue.asyncAfter(deadline:.now()+4) { [weak self] in
                    guard let self,self.epoch==generation,self.pendingRemote?.request==command.request else { return }
                    self.replyRemote(command,status:"rejected",reason:"failed")
                }
                return
            case ("lens",.text(let id)):
                guard let target=cameraDevices().first(where:{ $0.uniqueID==id }),let format=captureFormat(target) else {
                    replyRemote(command,status:"rejected",reason:"format");return
                }
                if target.uniqueID != device.uniqueID {
                    try switchCamera(target,format:format)
                    capabilityRevision+=1;forceKeyframe=true
                    sendCapabilities()
                }
            default:replyRemote(command,status:"rejected",reason:"unsupported");return
            }
            replyRemote(command,status:"applied")
        } catch { replyRemote(command,status:"rejected",reason:"failed") }
    }
    func switchCamera(_ device:AVCaptureDevice,format:AVCaptureDevice.Format) throws {
        let input=try AVCaptureDeviceInput(device:device)
        let oldInputs=capture.inputs.filter { $0.ports.contains { $0.mediaType == .video } }
        capture.beginConfiguration()
        do {
            for old in oldInputs { capture.removeInput(old) }
            guard capture.canAddInput(input) else { throw RemoteError.invalid }
            capture.addInput(input)
            try device.lockForConfiguration()
            device.activeFormat=format
            device.activeVideoMinFrameDuration=CMTime(value:1,timescale:mode.fps)
            device.activeVideoMaxFrameDuration=CMTime(value:1,timescale:mode.fps)
            device.activeColorSpace = .sRGB;device.automaticallyAdjustsVideoHDREnabled=false
            if format.isVideoHDRSupported { device.isVideoHDREnabled=false }
            device.unlockForConfiguration()
            capture.commitConfiguration();currentDevice=device
        } catch {
            for new in capture.inputs where new.ports.contains(where: { $0.mediaType == .video }) { capture.removeInput(new) }
            for old in oldInputs where capture.canAddInput(old) { capture.addInput(old) }
            capture.commitConfiguration()
            throw error
        }
    }
}
