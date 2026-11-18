import Foundation

enum PairingError: Error { case invalid }

struct PairingRecord: Codable, Equatable {
    let host: String
    let name: String
    let pin: String
    let token: String
    var serviceName: String { "UCS-" + String(pin.prefix(16)) }

    static func parse(_ value: String) throws -> PairingRecord {
        guard value.count <= 4096, let parts = URLComponents(string:value),
              parts.scheme?.lowercased() == "universalcamera", parts.host?.lowercased() == "pair",
              parts.user == nil, parts.password == nil, parts.port == nil,
              parts.path.isEmpty, parts.fragment == nil else { throw PairingError.invalid }
        let items = parts.queryItems ?? []
        let keys = Set(items.map(\.name))
        guard items.count == 5, keys == Set(["v","host","name","pin","token"]),
              items.allSatisfy({ $0.value != nil }) else { throw PairingError.invalid }
        let values = Dictionary(uniqueKeysWithValues: items.map { ($0.name,$0.value!) })
        guard values["v"] == "1" else { throw PairingError.invalid }
        let result = PairingRecord(host:values["host"]!,name:values["name"]!,
            pin:values["pin"]!.lowercased(),token:values["token"]!.lowercased())
        try result.validate()
        return result
    }

    func validate() throws {
        let pieces = host.split(separator:".",omittingEmptySubsequences:false).map(String.init)
        let numbers = pieces.compactMap(Int.init)
        guard numbers.count == 4, pieces.count == 4,
              zip(pieces,numbers).allSatisfy({ $0.0 == String($0.1) && (0...255).contains($0.1) }),
              numbers[0] == 10 || (numbers[0] == 172 && (16...31).contains(numbers[1])) ||
                (numbers[0] == 192 && numbers[1] == 168),
              !name.isEmpty, name.count <= 48,
              name == name.trimmingCharacters(in:.whitespacesAndNewlines),
              name.unicodeScalars.allSatisfy({ !CharacterSet.controlCharacters.contains($0) }) else {
            throw PairingError.invalid
        }
        let hex = CharacterSet(charactersIn:"0123456789abcdef")
        guard [pin,token].allSatisfy({ $0.count == 64 && $0.unicodeScalars.allSatisfy(hex.contains) }) else {
            throw PairingError.invalid
        }
    }
}
