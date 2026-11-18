import Foundation
import Network

/// Two local TCP endpoints carry TLS bytes across usbmux. TLS remains end-to-end
/// between Link and the desktop receiver; the relay never decrypts those bytes.
final class USBBridge {
    private let queue: DispatchQueue
    private var relayListener: NWListener?
    private var usbListener: NWListener?
    private var usb: NWConnection?
    private var relay: NWConnection?
    private var generation = UUID()
    var onReady: ((UInt16) -> Void)?
    var onError: ((String) -> Void)?
    init(queue:DispatchQueue) { self.queue = queue }

    private func loopback(_ port:NWEndpoint.Port) -> NWParameters {
        let tcp = NWProtocolTCP.Options(); tcp.noDelay = true
        let parameters = NWParameters(tls:nil,tcp:tcp)
        parameters.requiredLocalEndpoint = .hostPort(host:"127.0.0.1",port:port)
        parameters.allowLocalEndpointReuse = true
        return parameters
    }
    func start() {
        close()
        let epoch = generation
        do {
            let listener = try NWListener(using:loopback(.any))
            relayListener = listener
            listener.newConnectionHandler = { [weak self] conn in
                guard let self, self.generation == epoch, self.relay == nil, let usb = self.usb else { conn.cancel(); return }
                self.relay = conn
                conn.start(queue:self.queue)
                self.pump(from:conn,to:usb,epoch:epoch)
                self.pump(from:usb,to:conn,epoch:epoch)
            }
            listener.stateUpdateHandler = { [weak self] state in
                guard let self, self.generation == epoch else { return }
                if case .ready = state, let port = listener.port { self.listenUSB(relayPort:port.rawValue,epoch:epoch) }
                if case .failed = state { self.onError?("Nao foi possivel abrir o relay local USB.") }
            }
            listener.start(queue:queue)
        } catch { onError?("Nao foi possivel preparar o transporte USB.") }
    }
    private func listenUSB(relayPort:UInt16,epoch:UUID) {
        do {
            let listener = try NWListener(using:loopback(NWEndpoint.Port(rawValue:49201)!))
            usbListener = listener
            listener.newConnectionHandler = { [weak self] conn in
                guard let self, self.generation == epoch, self.usb == nil else { conn.cancel(); return }
                self.usb = conn
                conn.start(queue:self.queue)
                self.onReady?(relayPort)
            }
            listener.stateUpdateHandler = { [weak self] state in
                guard let self, self.generation == epoch else { return }
                if case .failed = state { self.onError?("Porta USB indisponivel. Pare outro app de camera e tente novamente.") }
            }
            listener.start(queue:queue)
        } catch { onError?("Nao foi possivel escutar a conexao por cabo.") }
    }
    private func pump(from source:NWConnection,to target:NWConnection,epoch:UUID) {
        source.receive(minimumIncompleteLength:1,maximumLength:65536) { [weak self] data,_,ended,error in
            guard let self, self.generation == epoch else { return }
            if let data, !data.isEmpty {
                target.send(content:data,completion:.contentProcessed { [weak self] sendError in
                    guard let self, self.generation == epoch else { return }
                    if sendError != nil || ended || error != nil { self.onError?("Cabo USB desconectado."); return }
                    self.pump(from:source,to:target,epoch:epoch)
                })
            } else if ended || error != nil { self.onError?("Cabo USB desconectado.") }
            else { self.pump(from:source,to:target,epoch:epoch) }
        }
    }
    func close() {
        generation = UUID()
        usb?.cancel();relay?.cancel();usbListener?.cancel();relayListener?.cancel()
        usb=nil;relay=nil;usbListener=nil;relayListener=nil
    }
}
