import Foundation
import Network
import CryptoKit
import Security

// All mutable state is confined to the caller's media queue.
final class Link {
    let queue: DispatchQueue
    var connection: NWConnection?
    var ready = false
    var buffer = Data()
    var onMic: ((Bool) -> Void)?
    private var micNegotiated = false
    var onReady: (() -> Void)?
    var onError: ((String) -> Void)?
    var onRTT: ((Double) -> Void)?
    var diagnostics: (() -> [String:Any])?
    var onControl: ((RemoteCommand) -> Void)?
    private(set) var controlSession:String?
    private var timingEnabled = false
    private var clock = ClockEstimate()
    private var ping: UInt64?
    private var timer: DispatchSourceTimer?
    init(queue: DispatchQueue) { self.queue = queue }

    func open(host: String, pin: String, token: String, endpoint: NWEndpoint? = nil, mode:VideoMode = .fullHD, allowMic:Bool = false) {
        close()
        let expected = pin.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        guard expected.count == 64, expected.allSatisfy({ $0.isHexDigit }),
              token.count == 64, token.allSatisfy({ $0.isHexDigit }) else {
            onError?("Pin e token devem ter 64 caracteres hexadecimais."); return
        }
        let tls = NWProtocolTLS.Options()
        sec_protocol_options_set_min_tls_protocol_version(tls.securityProtocolOptions, .TLSv12)
        sec_protocol_options_set_verify_block(tls.securityProtocolOptions, { _, trust, complete in
            let trustObject = sec_trust_copy_ref(trust).takeRetainedValue()
            guard let cert = SecTrustGetCertificateAtIndex(trustObject, 0) else { complete(false); return }
            let digest = SHA256.hash(data: SecCertificateCopyData(cert) as Data)
            complete(digest.map { String(format: "%02x", $0) }.joined() == expected)
        }, queue)
        let tcp = NWProtocolTCP.Options(); tcp.noDelay = true
        let parameters = NWParameters(tls: tls, tcp: tcp)
        parameters.prohibitedInterfaceTypes = [.cellular]
        let target = endpoint ?? NWEndpoint.hostPort(host:NWEndpoint.Host(host),port:49200)
        let conn = NWConnection(to:target,using:parameters)
        connection = conn
        conn.stateUpdateHandler = { [weak self, weak conn] state in
            guard let self, let conn, self.connection === conn else { return }
            switch state {
            case .ready:
                var hello: [String:Any] = ["token":token,"codec":"h264","width":Int(mode.width),
                    "height":Int(mode.height),"fps":Int(mode.fps),"pixel_format":"yuv420p","color":"bt709-sdr","timing":1,"controls":1]
                if allowMic { hello["mic"] = "pcm-s16le-v1" }
                do {
                    let data = try JSONSerialization.data(withJSONObject: hello)
                    self.send(Wire.packet(1, data)) { }
                    self.receive(conn,mode:mode,allowMic:allowMic)
                } catch { self.onError?(error.localizedDescription) }
            case .failed(let error): self.onError?(error.localizedDescription)
            default: break
            }
        }
        conn.start(queue: queue)
        queue.asyncAfter(deadline: .now()+8) { [weak self, weak conn] in
            guard let self, let conn, self.connection === conn, !self.ready else { return }
            self.onError?("Tempo de conexao/pareamento esgotado.")
        }
    }
    func receive(_ conn: NWConnection,mode:VideoMode,allowMic:Bool) {
        conn.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self, weak conn] data, _, ended, error in
            guard let self, let conn, self.connection === conn else { return }
            if let data { self.buffer.append(data) }
            while self.buffer.count >= 32 {
                let header = self.buffer
                let size = Int(Wire.number(header,8,4))
                guard Array(header.prefix(5)) == [85,67,83,49,1],
                      size <= 65536, Wire.number(header,6,2) == 0,
                      Wire.number(header,28,4) == 0 else {
                    self.onError?("Resposta de protocolo invalida."); return
                }
                guard self.buffer.count >= 32+size else { break }
                let type = header[5]
                let payload = self.buffer.subdata(in:32..<(32+size))
                self.buffer = Data(self.buffer.dropFirst(32+size))
                if type == 2 && !self.ready {
                    guard let obj = try? JSONSerialization.jsonObject(with: payload) as? [String:Any],
                          let version = obj["version"] as? Int, version == 1,
                          let stream = obj["stream"] as? [String:Any],
                          stream["codec"] as? String == "h264",
                          stream["width"] as? Int == Int(mode.width), stream["height"] as? Int == Int(mode.height),
                          stream["fps"] as? Int == Int(mode.fps) else {
                        self.onError?("Formato recusado pelo receptor."); return
                    }
                    self.timingEnabled = (obj["timing"] as? Int) == 1
                    if (obj["controls"] as? Int)==1, let session=obj["session"] as? String,
                       session.count==32,session.allSatisfy({ $0.isHexDigit }) { self.controlSession=session }
                    self.micNegotiated = allowMic && (obj["mic"] as? String) == "pcm-s16le-v1"
                    self.ready = true
                    let timer = DispatchSource.makeTimerSource(queue: self.queue)
                    timer.schedule(deadline: .now()+1, repeating: 1)
                    timer.setEventHandler { [weak self] in self?.heartbeat() }
                    self.timer = timer
                    timer.resume()
                    self.onReady?()
                } else if type == 11, self.ready, self.micNegotiated, payload.count == 1, let flag = payload.first, flag <= 1 {
                    self.onMic?(flag == 1)
                } else if type==8,self.ready,self.controlSession != nil {
                    do { self.onControl?(try RemoteCommand.parse(payload)) }
                    catch { self.onError?("Comando remoto invalido."); return }
                } else if type == 5, let sent = self.ping, Wire.number(header,20,8) == sent {
                    self.ping = nil
                    let now = DispatchTime.now().uptimeNanoseconds/1000
                    if self.timingEnabled {
                        guard payload.count == 16 else { self.onError?("Resposta de relogio invalida."); return }
                        self.clock.observe(t1:sent,t2:Wire.number(payload,0,8),t3:Wire.number(payload,8,8),t4:now)
                    }
                    self.onRTT?(Double(now-sent)/1000)
                } else { self.onError?("Mensagem inesperada."); return }
            }
            if ended || error != nil { self.onError?("Receptor desconectado."); return }
            self.receive(conn,mode:mode,allowMic:allowMic)
        }
    }
    func send(_ data: Data, completion: @escaping () -> Void) {
        guard let conn = connection else { completion(); return }
        conn.send(content: data, completion: .contentProcessed { [weak self, weak conn] error in
            guard let self, let conn, self.connection === conn else { return }
            completion()
            if let error { self.onError?(error.localizedDescription) }
        })
    }
    func sendControlJSON(_ type:UInt8,_ value:[String:Any]) {
        guard ready,controlSession != nil else { return }
        do {
            let data=try JSONSerialization.data(withJSONObject:value,options:[.sortedKeys])
            guard data.count<=65536 else { onError?("Resposta de controle excede o limite."); return }
            send(Wire.packet(type,data)) { }
        } catch { onError?("Falha ao preparar resposta de controle.") }
    }
    func heartbeat() {
        guard ready, ping == nil else { return }
        let stamp = DispatchTime.now().uptimeNanoseconds/1000; ping = stamp
        var payload = Data()
        if timingEnabled {
            var values = diagnostics?() ?? [:]
            if let offset = clock.offsetUs, let uncertainty = clock.uncertaintyUs {
                values["clock_offset_us"] = offset
                values["clock_uncertainty_us"] = uncertainty
            }
            payload = (try? JSONSerialization.data(withJSONObject:values)) ?? Data("{}".utf8)
        }
        send(Wire.packet(4, payload, pts:stamp)) { }
        queue.asyncAfter(deadline:.now()+5) { [weak self] in
            guard let self, self.ping == stamp else { return }
            self.onError?("Receptor sem resposta por 5 segundos.")
        }
    }
    func close() {
        timer?.cancel(); timer = nil
        clock = ClockEstimate(); timingEnabled = false
        micNegotiated=false
        controlSession=nil
        ready = false; connection?.cancel(); connection = nil; buffer.removeAll(); ping = nil
    }
}
