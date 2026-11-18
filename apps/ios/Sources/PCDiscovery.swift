import Foundation
import Network
import Combine

@MainActor final class PCDiscovery: ObservableObject {
    @Published private(set) var endpoint: NWEndpoint?
    private var browser: NWBrowser?
    private var generation = UUID()
    func find(_ record: PairingRecord?) {
        browser?.cancel(); browser = nil; endpoint = nil
        generation = UUID()
        guard let record else { return }
        let current = generation
        let parameters = NWParameters.tcp
        parameters.prohibitedInterfaceTypes = [.cellular]
        let browser = NWBrowser(for:.bonjour(type:"_ucs-camera._tcp",domain:nil),using:parameters)
        browser.browseResultsChangedHandler = { [weak self] results, _ in
            let found = results.first { result in
                if case let .service(name,_,_,_) = result.endpoint { return name.caseInsensitiveCompare(record.serviceName) == .orderedSame }
                return false
            }?.endpoint
            DispatchQueue.main.async {
                guard let self, self.generation == current else { return }
                self.endpoint = found
            }
        }
        browser.stateUpdateHandler = { [weak self] state in
            if case .failed = state {
                DispatchQueue.main.async {
                    guard let self, self.generation == current else { return }; self.endpoint = nil
                }
            }
        }
        self.browser = browser
        browser.start(queue:DispatchQueue(label:"ucs.discovery"))
    }
}
