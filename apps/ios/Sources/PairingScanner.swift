import SwiftUI
import AVFoundation

final class QRScannerEngine: NSObject, AVCaptureMetadataOutputObjectsDelegate {
    let session = AVCaptureSession()
    let queue = DispatchQueue(label:"ucs.pairing-scanner")
    var onResult: ((String) -> Void)?
    var onError: ((String) -> Void)?
    private var cancelled = false
    private var delivered = false
    func start() {
        AVCaptureDevice.requestAccess(for:.video) { [weak self] allowed in
            self?.queue.async { [weak self] in
                guard let self, !self.cancelled else { return }
                guard allowed else { self.fail("Permita a camera nos Ajustes para ler o QR."); return }
                do {
                    guard let device = AVCaptureDevice.default(.builtInWideAngleCamera,for:.video,position:.back) else {
                        self.fail("Camera indisponivel."); return
                    }
                    let input = try AVCaptureDeviceInput(device:device)
                    let output = AVCaptureMetadataOutput()
                    self.session.beginConfiguration()
                    if self.session.canSetSessionPreset(.hd1280x720) { self.session.sessionPreset = .hd1280x720 }
                    guard self.session.canAddInput(input) else {
                        self.session.commitConfiguration(); self.fail("Camera em uso. Pare a transmissao primeiro."); return
                    }
                    self.session.addInput(input)
                    guard self.session.canAddOutput(output) else {
                        self.session.commitConfiguration(); self.fail("Leitor QR indisponivel."); return
                    }
                    self.session.addOutput(output)
                    output.setMetadataObjectsDelegate(self,queue:self.queue)
                    output.metadataObjectTypes = [.qr]
                    self.session.commitConfiguration()
                    self.session.startRunning()
                } catch { self.fail("Nao foi possivel abrir a camera para parear.") }
            }
        }
    }
    func stop() { queue.async { self.cancelled = true; if self.session.isRunning { self.session.stopRunning() } } }
    private func fail(_ text: String) { DispatchQueue.main.async { self.onError?(text) } }
    func metadataOutput(_ output: AVCaptureMetadataOutput, didOutput metadataObjects:[AVMetadataObject], from connection:AVCaptureConnection) {
        guard !cancelled, !delivered,
              let code = metadataObjects.compactMap({ $0 as? AVMetadataMachineReadableCodeObject }).first,
              let value = code.stringValue else { return }
        delivered = true
        session.stopRunning()
        DispatchQueue.main.async { self.onResult?(value) }
    }
}

final class QRScannerController: UIViewController {
    let engine = QRScannerEngine()
    private var layer: AVCaptureVideoPreviewLayer?
    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        let layer = AVCaptureVideoPreviewLayer(session:engine.session)
        layer.videoGravity = .resizeAspectFill
        view.layer.addSublayer(layer); self.layer = layer
        engine.start()
    }
    override func viewDidLayoutSubviews() { super.viewDidLayoutSubviews(); layer?.frame = view.bounds }
    override func viewWillDisappear(_ animated:Bool) { super.viewWillDisappear(animated); engine.stop() }
}

struct PairingScanner: UIViewControllerRepresentable {
    let onResult: (String) -> Void
    let onError: (String) -> Void
    func makeUIViewController(context:Context) -> QRScannerController {
        let controller = QRScannerController()
        controller.engine.onResult = onResult; controller.engine.onError = onError
        return controller
    }
    func updateUIViewController(_ uiViewController:QRScannerController,context:Context) { }
    static func dismantleUIViewController(_ controller:QRScannerController,coordinator:()) { controller.engine.stop() }
}
