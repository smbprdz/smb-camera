import Foundation
import Combine
import Security

@MainActor final class PairingStore: ObservableObject {
    @Published private(set) var record: PairingRecord?
    @Published var error = ""
    private let query: [String:Any] = [kSecClass as String:kSecClassGenericPassword,
        kSecAttrService as String:"com.simbaproduz.universalcamera.pairing",
        kSecAttrAccount as String:"primary-pc"]

    init() {
        var request = query
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        let status = SecItemCopyMatching(request as CFDictionary,&item)
        if status == errSecItemNotFound { return }
        guard status == errSecSuccess, let data = item as? Data,
              let value = try? JSONDecoder().decode(PairingRecord.self,from:data) else {
            error = "Nao foi possivel recuperar o PC salvo. Leia o QR novamente."
            return
        }
        do { try value.validate(); record = value }
        catch { self.error = "O pareamento salvo nao e valido. Leia o QR novamente." }
    }

    func save(_ value: PairingRecord) {
        do {
            try value.validate()
            let data = try JSONEncoder().encode(value)
            let updates: [String:Any] = [kSecValueData as String:data,
                kSecAttrAccessible as String:kSecAttrAccessibleWhenUnlockedThisDeviceOnly]
            var status = SecItemUpdate(query as CFDictionary,updates as CFDictionary)
            if status == errSecItemNotFound {
                status = SecItemAdd(query.merging(updates) { _,new in new } as CFDictionary,nil)
            }
            guard status == errSecSuccess else {
                error = "Nao foi possivel salvar o pareamento neste iPhone. Tente novamente desbloqueado."
                return
            }
            record = value; error = ""
        } catch { self.error = "QR de pareamento invalido." }
    }

    func forget() {
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            error = "Nao foi possivel remover o PC salvo."; return
        }
        record = nil; error = ""
    }
}
