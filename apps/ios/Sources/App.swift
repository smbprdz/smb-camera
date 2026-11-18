import SwiftUI

@main @MainActor struct UniversalCameraApp: App {
    @StateObject private var camera = Camera()
    @StateObject private var screenMode = CameraScreenMode()
    @StateObject private var pairing = PairingStore()
    @StateObject private var discovery = PCDiscovery()
    @Environment(\.scenePhase) private var phase
    @State private var scanning = false
    @State private var scannedValue: String?
    @State private var pending: PairingRecord?
    @State private var confirmPairing = false
    @State private var scanError = ""
    @State private var allowMic = false
    @State private var cable = true
    @State private var videoMode:VideoMode = .fullHD

    var body: some Scene {
        WindowGroup {
            ZStack {
                if screenMode.covered {
                    Color.black.ignoresSafeArea().contentShape(Rectangle())
                        .onTapGesture(count:2) { screenMode.reveal() }
                        .accessibilityLabel("Camera transmitindo. Toque duas vezes para mostrar os controles.")
                        .accessibilityAddTraits(.isButton)
                        .accessibilityAction { screenMode.reveal() }
                } else {
                    NavigationStack {
                        Form {
                            if let pc = pairing.record {
                                Section("Seu PC") {
                                    Label(pc.name,systemImage:"desktopcomputer").font(.title2)
                                    Text(camera.isStreaming ? "PC conectado" : (discovery.endpoint == nil ? "PC salvo" : "PC encontrado na rede"))
                                        .foregroundStyle(.secondary)
                                    if camera.isStreaming {
                                        Button("Parar camera",role:.destructive) { camera.stop() }
                                        Button("Escurecer tela") { screenMode.cover() }
                                    } else {
                                        Picker("Conexao",selection:$cable) {
                                            Text("USB (cabo)").tag(true)
                                            Text("Wi-Fi").tag(false)
                                        }.pickerStyle(.segmented)
                                        Picker("Qualidade",selection:$videoMode) {
                                            ForEach(VideoMode.allCases) { Text($0.rawValue).tag($0) }
                                        }.pickerStyle(.segmented)
                                        Toggle("Permitir microfone ao gravar no PC", isOn:$allowMic)
                                        Button("Ativar camera") {
                                            camera.start(host:pc.host,pin:pc.pin,token:pc.token,endpoint:discovery.endpoint,
                                                         mode:videoMode,cable:cable,allowMic:allowMic)
                                        }.font(.headline)
                                    }
                                    Text(camera.status).font(.footnote).foregroundStyle(.secondary)
                                }
                                Section {
                                    Text("USB usa o cabo conectado ao PC. 4K30 depende da camera e do encoder. Ao transmitir, a tela fica preta; toque duas vezes para mostrar os controles.")
                                        .font(.footnote)
                                }
                                Section {
                                    Button("Parear outro PC") { scanning = true }.disabled(camera.isStreaming)
                                    Button("Esquecer PC",role:.destructive) { pairing.forget() }.disabled(camera.isStreaming)
                                }
                            } else {
                                Section("Conecte ao seu PC") {
                                    Label("Uma vez para parear. Depois, um toque para transmitir.",systemImage:"qrcode.viewfinder")
                                    Text("Abra o Universal Camera no PC e mostre o QR. Deixe o iPhone no Wi-Fi da mesma rede.")
                                    Button("Ler QR do PC") { scanning = true }.font(.headline)
                                }
                            }
                            if !scanError.isEmpty { Text(scanError).foregroundStyle(.red) }
                            if !pairing.error.isEmpty { Text(pairing.error).foregroundStyle(.red) }
                            if !camera.inventory.hasPrefix("Capacidades ainda") {
                                DisclosureGroup("Diagnostico da camera") {
                                    Text(camera.inventory).font(.caption).textSelection(.enabled)
                                }
                            }
                        }.navigationTitle("SMB Camera")
                    }
                }
            }
            .preferredColorScheme(.dark)
            .tint(Color(red:0.90,green:0.22,blue:0.54))
            .statusBarHidden(screenMode.covered)
            .persistentSystemOverlays(screenMode.covered ? .hidden : .automatic)
            .onAppear { discovery.find(pairing.record) }
            .onChange(of:pairing.record) { discovery.find($0) }
            .onChange(of:camera.isStreaming) { screenMode.setStreaming($0) }
            .onChange(of:phase) { value in
                screenMode.setActive(value == .active)
                if value == .background { camera.stop(); discovery.find(nil) }
                if value == .active { discovery.find(pairing.record) }
            }
            .sheet(isPresented:$scanning,onDismiss:acceptScan) {
                NavigationStack {
                    PairingScanner(onResult: { value in scannedValue = value; scanning = false },
                                   onError: { text in scanError = text; scanning = false })
                        .navigationTitle("Aponte para o QR no PC")
                        .toolbar { ToolbarItem(placement:.cancellationAction) { Button("Cancelar") { scanning = false } } }
                }
            }
            .alert("Usar este PC?",isPresented:$confirmPairing) {
                Button("Usar PC") { if let pending { pairing.save(pending) }; pending = nil }
                Button("Cancelar",role:.cancel) { pending = nil }
            } message: {
                Text("\(pending?.name ?? "PC") recebera a imagem quando voce tocar em Ativar camera.")
            }
        }
    }

    private func acceptScan() {
        guard let value = scannedValue else { return }
        scannedValue = nil
        do { pending = try PairingRecord.parse(value); scanError = ""; confirmPairing = true }
        catch { scanError = "Este QR nao e um pareamento valido do Universal Camera. Mostre o QR do aplicativo no seu PC." }
    }
}
